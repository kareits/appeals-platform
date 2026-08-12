"""Ticket-Service-backed adapter for the appeal-scope port.

Asks the Ticket Service, over its public API and with the **caller's own** bearer token, what that
caller may do with an appeal: ``GET /api/v1/tickets/{ticketId}/access`` returns the two decisions
the Ticket Service itself enforces (``canRead`` and the narrower ``canMutate``, ADR-0008).
Reading a document requires ``canRead``; attaching or moving evidence requires ``canMutate``, so an
audit role's broad read scope can never be borrowed for a write (CR-DOC-HIGH-002).

No policy is duplicated here, and no service identity is used: an adapter calling with a privileged
token would hand every document caller the privileges of the service. The probe is also not an
existence oracle — an appeal the caller cannot see and one that does not exist both answer ``false``
— so this service reports both as a plain denial.

Everything else fails closed as :class:`AppealScopeUnavailableError`: a timeout, a connection error,
a non-200 status, a wrong media type, a body missing either decision, or a decision issued for a
different appeal than the one asked about — a capability only means something together with the
resource it was issued for. An unavailable or unusable answer must never be read as consent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from mfo_http import PlatformHttpClient, is_json_media_type

from document_service.domain.scope import AppealScopeDeniedError, AppealScopeUnavailableError

_logger = logging.getLogger(__name__)

# Upper bound on the probe response body. The document is three small fields; anything larger means
# we are not talking to the endpoint we think we are.
_MAX_DECISION_BYTES = 4096

# The two capabilities the probe reports. Both must be present in every decision, whichever one the
# current operation needs.
_READ = "canRead"
_WRITE = "canMutate"


@dataclass(frozen=True)
class _Decision:
    """A validated authorization decision about one appeal.

    Attributes:
        ticket_id: The appeal the decision was issued for.
        can_read: Whether the caller may read that appeal.
        can_mutate: Whether the caller may modify it.
    """

    ticket_id: uuid.UUID
    can_read: bool
    can_mutate: bool


def _decode_decision(payload: dict[str, Any], expected_ticket_id: uuid.UUID) -> _Decision:
    """Validate a probe payload into a decision bound to the appeal it was requested for.

    An authorization capability is only meaningful together with the resource it was issued for, so
    the decision is rejected unless it carries **both** booleans and a ``ticketId`` equal to the one
    asked about. Without that binding, a partial, stale, misrouted, or wrongly cached 200 response
    could authorize a different appeal (CR-DOC-MEDIUM-004). Unknown extra fields are ignored: they
    are forward compatibility, not a decision.

    Args:
        payload: The decoded probe response body.
        expected_ticket_id: The appeal the caller asked about.

    Returns:
        The validated decision.

    Raises:
        AppealScopeUnavailableError: If a required field is missing or wrongly typed, or the
            decision refers to a different appeal. Never a denial: an unusable answer is not an
            answer.
    """
    raw_ticket_id = payload.get("ticketId")
    if not isinstance(raw_ticket_id, str):
        _logger.error("appeal-scope decision has no ticketId")
        raise AppealScopeUnavailableError("the appeal-scope decision is malformed")
    try:
        decided_ticket_id = uuid.UUID(raw_ticket_id)
    except ValueError as exc:
        _logger.error("appeal-scope decision has a malformed ticketId")
        raise AppealScopeUnavailableError("the appeal-scope decision is malformed") from exc
    if decided_ticket_id != expected_ticket_id:
        _logger.error(
            "appeal-scope decision is bound to %s but %s was requested",
            decided_ticket_id,
            expected_ticket_id,
        )
        raise AppealScopeUnavailableError("the appeal-scope decision is for another appeal")

    capabilities: dict[str, bool] = {}
    for field in (_READ, _WRITE):
        value = payload.get(field)
        if not isinstance(value, bool):
            _logger.error("appeal-scope decision is missing a boolean %s", field)
            raise AppealScopeUnavailableError("the appeal-scope decision is malformed")
        capabilities[field] = value
    return _Decision(
        ticket_id=decided_ticket_id,
        can_read=capabilities[_READ],
        can_mutate=capabilities[_WRITE],
    )


class TicketAppealScopeChecker:
    """Delegates appeal read/mutation decisions to the Ticket Service over HTTP."""

    def __init__(self, client: PlatformHttpClient) -> None:
        """Initialize the adapter.

        Args:
            client: HTTP client bound to the Ticket Service base URL. It propagates the correlation
                ID, so an authorization decision can be traced across both services.
        """
        self._client = client

    async def ensure_appeal_read_access(self, ticket_id: uuid.UUID, access_token: str) -> None:
        """Authorize reading an appeal's evidence.

        Args:
            ticket_id: The appeal the caller is trying to read.
            access_token: The caller's bearer token, forwarded verbatim.

        Raises:
            AppealScopeDeniedError: The Ticket Service reports the caller may not read the appeal.
            AppealScopeUnavailableError: The decision could not be obtained.
        """
        await self._require(ticket_id, access_token, capability=_READ)

    async def ensure_appeal_write_access(self, ticket_id: uuid.UUID, access_token: str) -> None:
        """Authorize modifying an appeal's evidence.

        Args:
            ticket_id: The appeal whose evidence the caller is trying to change.
            access_token: The caller's bearer token, forwarded verbatim.

        Raises:
            AppealScopeDeniedError: The Ticket Service reports the caller may not mutate the appeal.
            AppealScopeUnavailableError: The decision could not be obtained.
        """
        await self._require(ticket_id, access_token, capability=_WRITE)

    async def _require(self, ticket_id: uuid.UUID, access_token: str, *, capability: str) -> None:
        """Fetch the caller's capabilities on an appeal and require one of them.

        The whole decision is validated before the requested capability is read, so a partial
        document can never grant anything (CR-DOC-MEDIUM-004).

        Args:
            ticket_id: The appeal to evaluate.
            access_token: The caller's bearer token.
            capability: Which decision must be ``true`` (``canRead`` or ``canMutate``).

        Raises:
            AppealScopeDeniedError: The required capability is absent for this caller.
            AppealScopeUnavailableError: No trusted decision could be obtained.
        """
        payload = await self._fetch_decision(ticket_id, access_token)
        decision = _decode_decision(payload, ticket_id)
        if not (decision.can_read if capability == _READ else decision.can_mutate):
            raise AppealScopeDeniedError("the operation is not permitted on the referenced appeal")

    async def _fetch_decision(self, ticket_id: uuid.UUID, access_token: str) -> dict[str, Any]:
        """Call the Ticket access probe and return its decoded decision.

        Args:
            ticket_id: The appeal to evaluate.
            access_token: The caller's bearer token.

        Returns:
            The decoded decision object.

        Raises:
            AppealScopeUnavailableError: On any transport failure, unexpected status, wrong media
                type, oversized body, or unparsable payload. A 401 here means the two services
                disagree about a token this one already accepted (a signing-material or clock
                mismatch), which is an operational fault rather than a decision, and a 403 means the
                probe itself was refused — neither is a scope answer.
        """
        try:
            response = await self._client.request(
                "GET",
                f"/api/v1/tickets/{ticket_id}/access",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.TimeoutException as exc:
            raise AppealScopeUnavailableError("the appeal-scope decision timed out") from exc
        except httpx.HTTPError as exc:
            raise AppealScopeUnavailableError("the appeal-scope decision is unreachable") from exc

        if response.status_code != 200:
            _logger.error(
                "appeal-scope decision returned an unexpected status %s", response.status_code
            )
            raise AppealScopeUnavailableError("the appeal-scope decision is unavailable")
        if not is_json_media_type(response.headers.get("content-type", "")):
            _logger.error("appeal-scope decision returned a non-JSON media type")
            raise AppealScopeUnavailableError("the appeal-scope decision is malformed")
        if len(response.content) > _MAX_DECISION_BYTES:
            _logger.error("appeal-scope decision body is implausibly large")
            raise AppealScopeUnavailableError("the appeal-scope decision is malformed")
        try:
            decision = response.json()
        except ValueError as exc:
            raise AppealScopeUnavailableError("the appeal-scope decision is malformed") from exc
        if not isinstance(decision, dict):
            raise AppealScopeUnavailableError("the appeal-scope decision is malformed")
        return decision

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release its connections."""
        await self._client.aclose()


def create_scope_checker(base_url: str, timeout: httpx.Timeout | float) -> TicketAppealScopeChecker:
    """Build the Ticket-backed scope checker for the application.

    Args:
        base_url: Base URL of the Ticket Service.
        timeout: Request timeout; bounded so a slow decision point cannot pin a document request
            open indefinitely.

    Returns:
        The configured adapter.
    """
    return TicketAppealScopeChecker(PlatformHttpClient(base_url=base_url, timeout=timeout))

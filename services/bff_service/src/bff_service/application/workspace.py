"""Workspace aggregation for the appeal card.

Aggregates the appeal workspace the frontend renders from several downstream reads into one envelope
(BFF_SERVICE spec). In EP-1 only the Ticket Service exists, so the ticket card and comments are read
from it while the process, mail, and documents sections are placeholders for later phases.

Failures are classified explicitly rather than flattened to ``200 degraded`` (CR-BFF-HIGH-001):

- An authentication (401) or authorization (403) failure on **either** the card or comments is a
  critical request failure and is surfaced with that status — never hidden as a partial success.
- A missing appeal (card 404) is a 404; a card 429 is a 429 (preserving ``Retry-After``); a card
  timeout is a 504; a card connection failure is a 503; a card 5xx or malformed body is a safe 502.
- Only the genuinely optional ``comments`` section degrades: a non-auth comments failure marks that
  section ``unavailable`` and sets ``degraded=true`` while the rest of the workspace still returns.

Only expected transport and decoding errors are caught; cancellation and programming errors
propagate (they must never be swallowed as partial failures).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from mfo_http import PlatformHttpClient, is_json_media_type, read_bounded


class SectionStatus(StrEnum):
    """Read status of a workspace section.

    Attributes:
        OK: The section was read successfully and carries data.
        UNAVAILABLE: The section could not be read (a flagged partial failure); data is ``None``.
        NOT_IMPLEMENTED: The section is a placeholder for a later phase; data is ``None``.
    """

    OK = "ok"
    UNAVAILABLE = "unavailable"
    NOT_IMPLEMENTED = "not_implemented"


@dataclass(frozen=True)
class Section:
    """A single aggregated workspace section.

    Attributes:
        status: The read status of the section.
        data: The section payload when ``status`` is ``OK``; ``None`` otherwise.
    """

    status: SectionStatus
    data: Any = None


@dataclass(frozen=True)
class Workspace:
    """The aggregated appeal workspace.

    Attributes:
        ticket_id: The appeal identifier.
        degraded: ``True`` when an optional section could not be read (partial failure).
        ticket: The appeal card section.
        comments: The appeal comments section.
        process: The process section (placeholder in EP-1).
        mail: The mail-timeline section (placeholder in EP-1).
        documents: The documents section (placeholder in EP-1).
    """

    ticket_id: uuid.UUID
    degraded: bool
    ticket: Section
    comments: Section
    process: Section
    mail: Section
    documents: Section


class WorkspaceUnauthorizedError(Exception):
    """Raised when a downstream read reports the caller is unauthenticated (propagate as 401)."""


class WorkspaceForbiddenError(Exception):
    """Raised when a downstream read reports the caller lacks access (propagate as 403)."""


class WorkspaceTicketNotFoundError(Exception):
    """Raised when the aggregated appeal does not exist (Ticket Service returned 404)."""


class WorkspaceRateLimitedError(Exception):
    """Raised when a downstream read is rate limited (propagate as 429).

    Attributes:
        retry_after: The downstream ``Retry-After`` header value, if any.
    """

    def __init__(self, retry_after: str | None) -> None:
        """Initialize the error.

        Args:
            retry_after: The downstream ``Retry-After`` header value, if present.
        """
        super().__init__("the workspace read was rate limited")
        self.retry_after = retry_after


class WorkspaceUpstreamError(Exception):
    """Raised when a downstream read fails in a way that maps to a gateway 502/503/504.

    Attributes:
        status: The gateway status to return (502 bad gateway, 503 unavailable, 504 timeout).
    """

    def __init__(self, status: int, detail: str) -> None:
        """Initialize the error.

        Args:
            status: The gateway status to return.
            detail: A safe, non-leaking detail message.
        """
        super().__init__(detail)
        self.status = status


_PLACEHOLDER = Section(status=SectionStatus.NOT_IMPLEMENTED, data=None)
# Upper bound on a downstream section body the gateway will decode; a larger body is a protocol
# failure, not trusted data (CR-BFF-R3-MEDIUM-004).
_MAX_SECTION_BYTES = 2_000_000


@dataclass(frozen=True)
class _Read:
    """The settled outcome of a single downstream read (streamed under a byte ceiling).

    Attributes:
        status: The downstream status code, or ``None`` when the transport failed.
        content_type: The downstream ``Content-Type`` (empty on transport failure).
        body: The read body bytes on a bounded 200, or ``None`` (non-200, oversized, or failure).
        failure: ``"timeout"``/``"connection"``/``"oversized"`` when applicable, otherwise ``None``.
        retry_after: The downstream ``Retry-After`` header value, if any.
    """

    status: int | None
    content_type: str
    body: bytes | None
    failure: str | None
    retry_after: str | None


async def _read(client: PlatformHttpClient, path: str, token: str | None, max_bytes: int) -> _Read:
    """Stream a downstream GET under a hard byte ceiling via the shared bounded-read helper.

    Delegates to :func:`mfo_http.read_bounded` so the workspace shares one bounded-read
    implementation with the ordinary proxy and auth-context paths (CR-BFF-R6-HIGH-001). Only
    expected transport failures are reported (``timeout``/``connection``); cancellation and
    unexpected errors propagate. A 200 body larger than ``max_bytes`` is abandoned as ``oversized``.

    Args:
        client: The HTTP client bound to the downstream base URL.
        path: The request path.
        token: The caller's bearer access token, or ``None`` when absent.
        max_bytes: The maximum number of body bytes to read on a 200 response.

    Returns:
        The settled read outcome.
    """
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    bounded = await read_bounded(client, "GET", path, max_bytes=max_bytes, headers=headers)
    if bounded.failure is not None:
        return _Read(None, "", None, bounded.failure, None)
    content_type = bounded.headers.get("content-type", "")
    retry_after = bounded.headers.get("retry-after")
    if bounded.oversized:
        return _Read(bounded.status, content_type, None, "oversized", retry_after)
    return _Read(bounded.status, content_type, bounded.content, None, retry_after)


def _media_is_json(content_type: str) -> bool:
    """Return whether a ``Content-Type`` is exactly ``application/json`` (parameters ignored).

    Thin wrapper over the shared :func:`mfo_http.is_json_media_type` so every BFF trust boundary
    applies one exact media-type policy (CR-BFF-R6-MEDIUM-003).

    Args:
        content_type: The raw ``Content-Type`` header value.

    Returns:
        ``True`` when the media type is exactly ``application/json``.
    """
    return is_json_media_type(content_type)


def _raise_for_auth(status: int, retry_after: str | None) -> None:
    """Raise a critical request-level error for authentication/authorization/rate-limit statuses.

    Args:
        status: The downstream status code.
        retry_after: The downstream ``Retry-After`` header value, if any (for 429).

    Raises:
        WorkspaceUnauthorizedError: On 401.
        WorkspaceForbiddenError: On 403.
        WorkspaceRateLimitedError: On 429.
    """
    if status == 401:
        raise WorkspaceUnauthorizedError("the workspace read was not authenticated")
    if status == 403:
        raise WorkspaceForbiddenError("the workspace read was not authorized")
    if status == 429:
        raise WorkspaceRateLimitedError(retry_after)


def _classify_card(read: _Read) -> Section:
    """Classify the appeal-card read; the card is the core section, so failures are request-level.

    Args:
        read: The settled card read.

    Returns:
        The ``OK`` card section.

    Raises:
        WorkspaceUpstreamError: 504 on timeout, 503 on connection failure, 502 on
            oversized/5xx/unexpected media type/invalid JSON/invalid shape.
        WorkspaceUnauthorizedError: On 401.
        WorkspaceForbiddenError: On 403.
        WorkspaceTicketNotFoundError: On 404.
        WorkspaceRateLimitedError: On 429.
    """
    if read.failure == "timeout":
        raise WorkspaceUpstreamError(504, "the ticket service timed out")
    if read.failure == "connection":
        raise WorkspaceUpstreamError(503, "the ticket service is unavailable")
    if read.failure == "oversized":
        raise WorkspaceUpstreamError(502, "the ticket service returned an oversized card")
    assert read.status is not None
    status = read.status
    if status == 200:
        if not _media_is_json(read.content_type):
            raise WorkspaceUpstreamError(
                502, "the ticket service returned an unexpected media type"
            )
        assert read.body is not None
        try:
            value = json.loads(read.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WorkspaceUpstreamError(
                502, "the ticket service returned a malformed card"
            ) from exc
        if not isinstance(value, dict) or "id" not in value:
            raise WorkspaceUpstreamError(
                502, "the ticket service returned an unexpected card shape"
            )
        return Section(status=SectionStatus.OK, data=value)
    _raise_for_auth(status, read.retry_after)
    if status == 404:
        raise WorkspaceTicketNotFoundError("the appeal does not exist")
    raise WorkspaceUpstreamError(502, "the ticket service returned an error")


def _valid_comments(value: Any) -> bool:
    """Return whether a decoded comments body matches the minimal transport envelope.

    The body must be a list whose every item is an object carrying at least an ``id``; a primitive
    item or an object without the envelope is rejected so it is not marked ``ok`` (R4-MEDIUM-002).

    Args:
        value: The decoded comments value.

    Returns:
        ``True`` when the value is a valid comments list.
    """
    return isinstance(value, list) and all(
        isinstance(item, dict) and "id" in item for item in value
    )


def _classify_comments(read: _Read) -> Section:
    """Classify the comments read; comments are optional, so non-auth failures degrade.

    Args:
        read: The settled comments read.

    Returns:
        The ``OK`` or ``UNAVAILABLE`` comments section.

    Raises:
        WorkspaceUnauthorizedError: On 401 (authentication failure is never hidden).
        WorkspaceForbiddenError: On 403 (authorization failure is never hidden).
    """
    _unavailable = Section(status=SectionStatus.UNAVAILABLE, data=None)
    # Transport failure or an oversized/aborted body degrades the optional section.
    if read.failure is not None or read.status is None:
        return _unavailable
    if read.status != 200:
        # An authentication/authorization failure is critical even for comments and is propagated;
        # any other non-200 (including 429/5xx) degrades the optional section.
        if read.status == 401:
            raise WorkspaceUnauthorizedError("the workspace read was not authenticated")
        if read.status == 403:
            raise WorkspaceForbiddenError("the workspace read was not authorized")
        return _unavailable
    # A 200 with a wrong media type, invalid JSON, or an invalid list/item shape degrades the
    # section rather than failing the request (CR-BFF-R4-MEDIUM-002).
    if read.body is None or not _media_is_json(read.content_type):
        return _unavailable
    try:
        value = json.loads(read.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _unavailable
    if not _valid_comments(value):
        return _unavailable
    return Section(status=SectionStatus.OK, data=value)


async def build_workspace(
    ticket_client: PlatformHttpClient, ticket_id: uuid.UUID, token: str | None
) -> Workspace:
    """Aggregate the appeal workspace from the Ticket Service with explicit failure classification.

    The card and comments are read concurrently. Authentication/authorization failures and critical
    card failures are raised (and mapped to the matching HTTP status by the route); only optional
    comments failures degrade.

    Args:
        ticket_client: The HTTP client bound to the Ticket Service base URL.
        ticket_id: The appeal identifier.
        token: The caller's bearer access token, forwarded downstream.

    Returns:
        The aggregated workspace, possibly degraded.

    Raises:
        WorkspaceUnauthorizedError: On a downstream 401.
        WorkspaceForbiddenError: On a downstream 403.
        WorkspaceTicketNotFoundError: When the appeal does not exist.
        WorkspaceRateLimitedError: On a card 429.
        WorkspaceUpstreamError: On a card timeout/connection/5xx/malformed response.
    """
    card_read, comments_read = await asyncio.gather(
        _read(ticket_client, f"/api/v1/tickets/{ticket_id}", token, _MAX_SECTION_BYTES),
        _read(ticket_client, f"/api/v1/tickets/{ticket_id}/comments", token, _MAX_SECTION_BYTES),
    )

    ticket_section = _classify_card(card_read)
    comments_section = _classify_comments(comments_read)
    degraded = comments_section.status is SectionStatus.UNAVAILABLE

    return Workspace(
        ticket_id=ticket_id,
        degraded=degraded,
        ticket=ticket_section,
        comments=comments_section,
        process=_PLACEHOLDER,
        mail=_PLACEHOLDER,
        documents=_PLACEHOLDER,
    )

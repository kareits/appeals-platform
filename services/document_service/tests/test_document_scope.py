"""Object-level authorization tests: every operation demands an appeal-scope decision.

Regression suite for CR-DOC-HIGH-001. Holding ``ticket:read`` is not enough to reach an arbitrary
appeal's evidence: the service must ask the authority that owns the appeal scope (the Ticket
Service, ADR-0008) with the caller's own token, and must fail closed when that answer is negative
or unavailable. :class:`FakeScopeChecker` stands in for the Ticket Service and records what was
asked; the second half of this module tests the real adapter against a mock transport.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from document_service.config import Settings
from document_service.domain.scope import AppealScopeDeniedError, AppealScopeUnavailableError
from document_service.infrastructure.ticket_scope import TicketAppealScopeChecker
from document_service.main import create_app
from document_test_support import (
    DEFAULT_SUBJECT,
    FakeScopeChecker,
    build_settings,
    create_schema,
    mint_token,
)
from httpx import AsyncClient
from mfo_http import PlatformHttpClient
from mfo_testing import create_asgi_client

_FILE = {"file": ("evidence.pdf", b"%PDF-1.4 evidence", "application/pdf")}


@contextlib.asynccontextmanager
async def _service(
    tmp_path: Path, checker: FakeScopeChecker, *, token: str | None = None
) -> AsyncIterator[tuple[AsyncClient, Settings]]:
    """Run the service over a fresh database with a given scope stand-in.

    Args:
        tmp_path: Pytest-provided temporary directory.
        checker: The appeal-scope stand-in to wire in.
        token: Optional bearer token; defaults to the standard test caller.

    Yields:
        An authenticated HTTP client and the settings it runs with.
    """
    settings: Settings = build_settings(tmp_path)
    await create_schema(settings.database_url)
    app = create_app(settings, scope_checker=checker)
    async with create_asgi_client(app) as client:
        client.headers["Authorization"] = f"Bearer {token or mint_token()}"
        yield client, settings


async def test_upload_to_an_appeal_out_of_scope_is_denied(tmp_path: Path) -> None:
    """A caller who may not reach the appeal cannot attach evidence to it, and nothing is stored."""
    denied_ticket = uuid.uuid4()
    checker = FakeScopeChecker(denied={denied_ticket})

    async with _service(tmp_path, checker) as (client, settings):
        response = await client.post(
            "/api/v1/documents", files=_FILE, data={"ticketId": str(denied_ticket)}
        )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    # A write must be authorized as a write, not as a read (CR-DOC-HIGH-002).
    assert checker.write_calls[0][0] == denied_ticket
    assert checker.read_calls == []
    # Fail-closed before any write: no stored object was created.
    assert not [path for path in Path(settings.storage_root).rglob("*") if path.is_file()]


async def test_listing_another_appeal_is_denied(tmp_path: Path) -> None:
    """Listing is scoped: a caller-chosen ticketId out of scope yields 403, never a page."""
    denied_ticket = uuid.uuid4()
    checker = FakeScopeChecker(denied={denied_ticket})

    async with _service(tmp_path, checker) as (client, _settings):
        response = await client.get("/api/v1/documents", params={"ticketId": str(denied_ticket)})

    assert response.status_code == 403
    assert [call[0] for call in checker.read_calls] == [denied_ticket]


async def test_reading_and_downloading_another_appeals_document_is_denied(tmp_path: Path) -> None:
    """The reviewer's scenario: a caller outside the scope reads neither metadata nor bytes."""
    ticket_a = uuid.uuid4()
    checker = FakeScopeChecker()

    async with _service(tmp_path, checker) as (client, _settings):
        created = await client.post(
            "/api/v1/documents", files=_FILE, data={"ticketId": str(ticket_a)}
        )
        assert created.status_code == 201
        document_id = created.json()["id"]

        # The appeal is now out of scope for this caller (the other user's decision).
        checker.deny(ticket_a)

        metadata = await client.get(f"/api/v1/documents/{document_id}")
        content = await client.get(f"/api/v1/documents/{document_id}/content")

    assert metadata.status_code == 403
    assert content.status_code == 403
    # The denial must not leak the document's contents or filename.
    assert "evidence.pdf" not in metadata.text


async def test_unlinked_document_is_visible_only_to_its_uploader(tmp_path: Path) -> None:
    """With no appeal to decide on, an unlinked document stays private to the uploader."""
    checker = FakeScopeChecker()
    other_subject = uuid.uuid4()

    async with _service(tmp_path, checker) as (client, _settings):
        created = await client.post("/api/v1/documents", files=_FILE)
        assert created.status_code == 201
        document_id = created.json()["id"]

        mine = await client.get(f"/api/v1/documents/{document_id}")
        theirs = await client.get(
            f"/api/v1/documents/{document_id}",
            headers={"Authorization": f"Bearer {mint_token(subject=other_subject)}"},
        )

    assert mine.status_code == 200
    assert theirs.status_code == 403
    # No appeal exists, so no scope decision was requested for either caller.
    assert checker.calls == []


async def test_linking_requires_access_to_the_destination_appeal(tmp_path: Path) -> None:
    """A document may only be attached to an appeal the caller can reach."""
    denied_ticket = uuid.uuid4()
    checker = FakeScopeChecker(denied={denied_ticket})

    async with _service(tmp_path, checker) as (client, _settings):
        created = await client.post("/api/v1/documents", files=_FILE)
        document_id = created.json()["id"]

        response = await client.post(
            f"/api/v1/documents/{document_id}/link", json={"ticketId": str(denied_ticket)}
        )
        after = await client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 403
    # Still unlinked: the refused link changed nothing.
    assert after.json()["ticketId"] is None


async def test_scope_decision_is_made_with_the_callers_own_token(tmp_path: Path) -> None:
    """The caller's bearer token is forwarded, so the decision uses their privileges, not ours."""
    ticket_id = uuid.uuid4()
    checker = FakeScopeChecker()
    token = mint_token(subject=DEFAULT_SUBJECT)

    async with _service(tmp_path, checker, token=token) as (client, _settings):
        response = await client.get("/api/v1/documents", params={"ticketId": str(ticket_id)})

    assert response.status_code == 200
    assert checker.read_calls == [(ticket_id, token)]


async def test_unavailable_scope_decision_fails_closed_on_read(tmp_path: Path) -> None:
    """When the decision point is unreachable a read is refused with 503, never allowed."""
    checker = FakeScopeChecker(unavailable=True)

    async with _service(tmp_path, checker) as (client, _settings):
        response = await client.get("/api/v1/documents", params={"ticketId": str(uuid.uuid4())})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    # Reported as unavailable, not as a denial: an outage must not masquerade as a policy decision.
    assert "unavailable" in response.json()["detail"]


async def test_unavailable_scope_decision_fails_closed_on_upload(tmp_path: Path) -> None:
    """An upload naming an appeal is refused with 503 and stores nothing."""
    checker = FakeScopeChecker(unavailable=True)

    async with _service(tmp_path, checker) as (client, settings):
        response = await client.post(
            "/api/v1/documents", files=_FILE, data={"ticketId": str(uuid.uuid4())}
        )

    assert response.status_code == 503
    assert not [path for path in Path(settings.storage_root).rglob("*") if path.is_file()]


def _adapter_over(handler: httpx.MockTransport) -> TicketAppealScopeChecker:
    """Build a Ticket-backed checker over a mock transport.

    Args:
        handler: The mock transport serving the Ticket Service responses.

    Returns:
        The adapter under test.
    """
    return TicketAppealScopeChecker(
        PlatformHttpClient(client=httpx.AsyncClient(transport=handler, base_url="http://ticket"))
    )


async def test_adapter_asks_the_probe_and_reads_the_right_capability() -> None:
    """The adapter calls the access probe and evaluates ``canRead`` or ``canMutate`` accordingly.

    The decisive case for CR-DOC-HIGH-002: one probe response that grants read but not mutation must
    allow a read and refuse a write.
    """
    ticket_id = uuid.uuid4()
    seen: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        """Record the request and answer readable-but-not-mutable.

        Args:
            request: The outbound request.

        Returns:
            The access decision.
        """
        seen.append(request)
        return httpx.Response(
            200, json={"ticketId": str(ticket_id), "canRead": True, "canMutate": False}
        )

    checker = _adapter_over(httpx.MockTransport(_handler))

    await checker.ensure_appeal_read_access(ticket_id, "caller-token")
    with pytest.raises(AppealScopeDeniedError):
        await checker.ensure_appeal_write_access(ticket_id, "caller-token")
    await checker.aclose()

    assert len(seen) == 2
    assert seen[0].url.path == f"/api/v1/tickets/{ticket_id}/access"
    assert seen[0].headers["authorization"] == "Bearer caller-token"


async def test_adapter_allows_a_write_when_the_probe_grants_mutation() -> None:
    """A caller Ticket reports as able to mutate may write."""
    ticket_id = uuid.uuid4()
    checker = _adapter_over(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ticketId": str(ticket_id), "canRead": True, "canMutate": True}
            )
        )
    )

    await checker.ensure_appeal_write_access(ticket_id, "caller-token")
    await checker.aclose()


async def test_adapter_denies_when_the_probe_reports_no_access() -> None:
    """An appeal the caller cannot see — or that does not exist — is a plain denial."""
    ticket_id = uuid.uuid4()
    checker = _adapter_over(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ticketId": str(ticket_id), "canRead": False, "canMutate": False}
            )
        )
    )

    with pytest.raises(AppealScopeDeniedError):
        await checker.ensure_appeal_read_access(ticket_id, "caller-token")
    await checker.aclose()


@pytest.mark.parametrize("status", [401, 403, 404, 204, 302, 500, 502])
async def test_adapter_fails_closed_on_a_non_200_probe(status: int) -> None:
    """Only a 200 decision document is an answer; any other status is "unavailable".

    The probe answers 200 with two booleans even for an appeal the caller cannot see, so a non-200
    means an operational fault — a refused probe, a signing mismatch, an outage — never a scope
    decision.
    """
    checker = _adapter_over(httpx.MockTransport(lambda request: httpx.Response(status)))

    with pytest.raises(AppealScopeUnavailableError):
        await checker.ensure_appeal_read_access(uuid.uuid4(), "caller-token")
    await checker.aclose()


# Decision documents that must never authorize anything, whichever capability is being checked.
# ``{ticket}`` is substituted with the appeal actually being asked about (CR-DOC-MEDIUM-004).
_UNUSABLE_DECISIONS = [
    pytest.param({"ticketId": "{ticket}", "canMutate": True}, id="missing-canRead"),
    pytest.param({"ticketId": "{ticket}", "canRead": True}, id="missing-canMutate"),
    pytest.param({"canRead": True, "canMutate": True}, id="missing-ticketId"),
    pytest.param(
        {"ticketId": "not-a-uuid", "canRead": True, "canMutate": True}, id="malformed-ticketId"
    ),
    pytest.param({"ticketId": 12345, "canRead": True, "canMutate": True}, id="non-string-ticketId"),
    pytest.param(
        {"ticketId": "{ticket}", "canRead": "yes", "canMutate": "no"}, id="non-boolean-flags"
    ),
    pytest.param({"ticketId": "{ticket}", "canRead": 1, "canMutate": 1}, id="integer-flags"),
    pytest.param({}, id="empty"),
    pytest.param([], id="not-an-object"),
]


def _decision_for(payload: object, ticket_id: uuid.UUID) -> object:
    """Substitute the real appeal identifier into a decision template.

    Args:
        payload: The template payload.
        ticket_id: The appeal being asked about.

    Returns:
        The payload with ``{ticket}`` replaced by the appeal identifier.
    """
    if isinstance(payload, dict) and payload.get("ticketId") == "{ticket}":
        return {**payload, "ticketId": str(ticket_id)}
    return payload


@pytest.mark.parametrize("payload", _UNUSABLE_DECISIONS)
@pytest.mark.parametrize("capability", ["read", "write"])
async def test_adapter_fails_closed_on_an_incomplete_decision(
    payload: object, capability: str
) -> None:
    """A decision is trusted only when it is complete: both booleans plus the appeal it belongs to.

    Regression guard for CR-DOC-MEDIUM-004, checked through **both** entry points — previously each
    method validated only the flag it happened to need, so ``{"canRead": true}`` authorized a read
    and ``{"canMutate": true}`` authorized a write with no identifier and no second flag.
    """
    ticket_id = uuid.uuid4()
    checker = _adapter_over(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json=_decision_for(payload, ticket_id))
        )
    )

    with pytest.raises(AppealScopeUnavailableError):
        if capability == "read":
            await checker.ensure_appeal_read_access(ticket_id, "caller-token")
        else:
            await checker.ensure_appeal_write_access(ticket_id, "caller-token")
    await checker.aclose()


@pytest.mark.parametrize("capability", ["read", "write"])
async def test_adapter_rejects_a_decision_about_another_appeal(capability: str) -> None:
    """A capability is bound to the appeal it was issued for, or it is worthless.

    A complete, fully permissive decision that names a *different* appeal — a stale, misrouted, or
    wrongly cached response — must not authorize the appeal actually being asked about.
    """
    requested = uuid.uuid4()
    other = uuid.uuid4()
    checker = _adapter_over(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"ticketId": str(other), "canRead": True, "canMutate": True}
            )
        )
    )

    with pytest.raises(AppealScopeUnavailableError):
        if capability == "read":
            await checker.ensure_appeal_read_access(requested, "caller-token")
        else:
            await checker.ensure_appeal_write_access(requested, "caller-token")
    await checker.aclose()


@pytest.mark.parametrize("capability", ["read", "write"])
async def test_adapter_accepts_a_complete_decision_for_the_exact_appeal(capability: str) -> None:
    """The positive case: a complete decision naming exactly the requested appeal authorizes it."""
    ticket_id = uuid.uuid4()
    checker = _adapter_over(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "ticketId": str(ticket_id),
                    "canRead": True,
                    "canMutate": True,
                    # An unknown field is forward compatibility, not a decision: it is ignored.
                    "policyVersion": "v1",
                },
            )
        )
    )

    if capability == "read":
        await checker.ensure_appeal_read_access(ticket_id, "caller-token")
    else:
        await checker.ensure_appeal_write_access(ticket_id, "caller-token")
    await checker.aclose()


async def test_adapter_fails_closed_on_a_non_json_decision() -> None:
    """An HTML error page (from a proxy, say) is never parsed as an allow."""
    checker = _adapter_over(
        httpx.MockTransport(
            lambda request: httpx.Response(
                200, text="<html>ok</html>", headers={"content-type": "text/html"}
            )
        )
    )

    with pytest.raises(AppealScopeUnavailableError):
        await checker.ensure_appeal_read_access(uuid.uuid4(), "caller-token")
    await checker.aclose()


@pytest.mark.parametrize("error", ["timeout", "connect"])
async def test_adapter_fails_closed_on_transport_errors(error: str) -> None:
    """A timeout or connection failure never becomes an allow."""

    def _handler(request: httpx.Request) -> httpx.Response:
        """Raise the configured transport failure.

        Args:
            request: The outbound request.

        Returns:
            Never returns.

        Raises:
            httpx.ReadTimeout: When the parametrized error is a timeout.
            httpx.ConnectError: When the parametrized error is a connection failure.
        """
        if error == "timeout":
            raise httpx.ReadTimeout("decision timed out", request=request)
        raise httpx.ConnectError("decision unreachable", request=request)

    checker = _adapter_over(httpx.MockTransport(_handler))

    with pytest.raises(AppealScopeUnavailableError):
        await checker.ensure_appeal_read_access(uuid.uuid4(), "caller-token")
    await checker.aclose()


# --- Writes require a mutation decision, never a read one (CR-DOC-HIGH-002) ----------------------


async def test_upload_needs_mutation_scope_not_read_scope(tmp_path: Path) -> None:
    """A caller who may read an appeal but not modify it cannot attach evidence to it.

    This is the composite-role escalation: ``AUDITOR`` lends organization-wide (and confidential)
    read scope while ``EMPLOYEE`` lends the ``ticket:update`` permission. Ticket refuses the
    mutation, so the document service must refuse the upload — and must store nothing.
    """
    readable_only = uuid.uuid4()
    checker = FakeScopeChecker(write_denied={readable_only})

    async with _service(tmp_path, checker) as (client, settings):
        upload = await client.post(
            "/api/v1/documents", files=_FILE, data={"ticketId": str(readable_only)}
        )
        listed = await client.get("/api/v1/documents", params={"ticketId": str(readable_only)})

    assert upload.status_code == 403
    # Reading the same appeal's documents is still allowed: only the write is refused.
    assert listed.status_code == 200
    assert not [path for path in Path(settings.storage_root).rglob("*") if path.is_file()]


async def test_link_needs_mutation_scope_on_the_destination(tmp_path: Path) -> None:
    """Evidence cannot be attached to an appeal the caller may read but not modify."""
    readable_only = uuid.uuid4()
    checker = FakeScopeChecker(write_denied={readable_only})

    async with _service(tmp_path, checker) as (client, _settings):
        created = await client.post("/api/v1/documents", files=_FILE)
        document_id = created.json()["id"]

        response = await client.post(
            f"/api/v1/documents/{document_id}/link", json={"ticketId": str(readable_only)}
        )
        after = await client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 403
    assert after.json()["ticketId"] is None


async def test_link_needs_mutation_scope_on_the_current_appeal(tmp_path: Path) -> None:
    """A document already attached to an appeal cannot be moved by a read-only-scoped caller.

    Moving evidence changes the record of the appeal it is attached to, so that side needs a
    mutation decision too — otherwise an audit-scoped caller could detach evidence from an appeal
    they may only observe.
    """
    current = uuid.uuid4()
    destination = uuid.uuid4()
    checker = FakeScopeChecker()

    async with _service(tmp_path, checker) as (client, _settings):
        created = await client.post(
            "/api/v1/documents", files=_FILE, data={"ticketId": str(current)}
        )
        document_id = created.json()["id"]

        # From now on the caller may read the current appeal but not modify it.
        checker.deny_write(current)
        response = await client.post(
            f"/api/v1/documents/{document_id}/link", json={"ticketId": str(destination)}
        )

    assert response.status_code == 403
    # The destination was never consulted: the first refusal stops the operation.
    assert destination not in [ticket for ticket, _token in checker.write_calls]


async def test_reads_still_use_the_read_decision(tmp_path: Path) -> None:
    """Metadata and content reads ask the read question, so audit roles keep their visibility."""
    readable_only = uuid.uuid4()
    checker = FakeScopeChecker()

    async with _service(tmp_path, checker) as (client, _settings):
        created = await client.post(
            "/api/v1/documents", files=_FILE, data={"ticketId": str(readable_only)}
        )
        document_id = created.json()["id"]
        checker.deny_write(readable_only)

        metadata = await client.get(f"/api/v1/documents/{document_id}")
        content = await client.get(f"/api/v1/documents/{document_id}/content")

    assert metadata.status_code == 200
    assert content.status_code == 200

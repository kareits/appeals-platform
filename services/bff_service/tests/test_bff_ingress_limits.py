"""Ingress body-limit tests for the gateway.

An oversized request must be rejected with a sanitized ``413`` before the body is fully buffered and
before any downstream call, so the public gateway cannot be driven to allocate attacker-controlled
memory and an unsafe mutation is never partially forwarded (CR-BFF-R6-HIGH-001). The limit applies
to both a declared ``Content-Length`` and a chunked body with no length.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from bff_fakes import ClientFactory, Handler, auth_me_handler, new_ticket_id

# A tiny ingress ceiling keeps the oversized-body payloads small and fast.
_LIMIT = 200


@pytest.fixture(autouse=True)
def _tiny_ingress_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the ingress ceiling for this module so oversized bodies stay small.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
    """
    monkeypatch.setenv("BFF_MAX_REQUEST_BYTES", str(_LIMIT))


def _recording_ticket_handler(calls: list[str]) -> Handler:
    """Build a Ticket handler that records that it was called and returns a created card.

    Args:
        calls: A list appended to on every downstream call.

    Returns:
        A mock-transport handler.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        """Record the call and return a minimal created card.

        Args:
            request: The incoming request.

        Returns:
            A 201 JSON response.
        """
        calls.append(request.url.path)
        return httpx.Response(201, json={"id": str(new_ticket_id())})

    return _handler


async def _chunks(total: int, *, size: int = 64) -> AsyncIterator[bytes]:
    """Yield a chunked body of ``total`` bytes with no Content-Length (chunked transfer).

    Args:
        total: The total number of body bytes to emit.
        size: The per-chunk size.

    Yields:
        Successive byte chunks.
    """
    sent = 0
    while sent < total:
        chunk = b"x" * min(size, total - sent)
        sent += len(chunk)
        yield chunk


async def test_oversized_content_length_is_413_before_downstream(
    build_client: ClientFactory,
) -> None:
    """A declared Content-Length over the limit is rejected with 413 before any downstream call."""
    calls: list[str] = []
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:create",)),
        ticket_handler=_recording_ticket_handler(calls),
    )
    response = await client.post(
        "/api/v1/tickets",
        content=b"y" * (_LIMIT + 1),
        headers={"Authorization": "Bearer good", "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "x-correlation-id" in {k.lower() for k in response.headers}
    assert calls == []  # the mutation never reached the Ticket Service


async def test_oversized_chunked_body_is_413_before_downstream(
    build_client: ClientFactory,
) -> None:
    """A chunked body (no Content-Length) over the limit is rejected with 413, not forwarded."""
    calls: list[str] = []
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:create",)),
        ticket_handler=_recording_ticket_handler(calls),
    )
    response = await client.post(
        "/api/v1/tickets",
        content=_chunks(_LIMIT + 256),
        headers={"Authorization": "Bearer good", "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert calls == []


async def test_body_exactly_at_limit_is_forwarded(build_client: ClientFactory) -> None:
    """A body of exactly the limit is accepted and forwarded to the Ticket Service."""
    calls: list[str] = []
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:create",)),
        ticket_handler=_recording_ticket_handler(calls),
    )
    response = await client.post(
        "/api/v1/tickets",
        content=b"y" * _LIMIT,
        headers={"Authorization": "Bearer good", "content-type": "application/json"},
    )
    assert response.status_code == 201
    assert calls == ["/api/v1/tickets"]


async def test_body_one_byte_over_limit_is_413(build_client: ClientFactory) -> None:
    """A body one byte over the limit is rejected with 413."""
    calls: list[str] = []
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:create",)),
        ticket_handler=_recording_ticket_handler(calls),
    )
    response = await client.post(
        "/api/v1/tickets",
        content=b"y" * (_LIMIT + 1),
        headers={"Authorization": "Bearer good", "content-type": "application/json"},
    )
    assert response.status_code == 413
    assert calls == []


async def test_oversized_login_body_is_413_before_iam(build_client: ClientFactory) -> None:
    """The public login endpoint rejects an oversized body with 413 before calling IAM."""
    calls: list[str] = []

    def _iam(request: httpx.Request) -> httpx.Response:
        """Record any IAM call.

        Args:
            request: The incoming request.

        Returns:
            A token document (should never be reached in this test).
        """
        calls.append(request.url.path)
        return httpx.Response(200, json={"accessToken": "x"})

    client = await build_client(iam_handler=_iam)
    response = await client.post("/api/v1/auth/login", content=b"y" * (_LIMIT + 1))
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert calls == []

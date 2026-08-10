"""Gateway passthrough tests for the BFF ticket routes.

Covers request forwarding (body, idempotency key, bearer token, correlation ID), gateway permission
enforcement, downstream error relay, and downstream-outage mapping.
"""

from __future__ import annotations

from typing import Any

import httpx
from bff_fakes import ClientFactory, Handler, auth_me_handler, new_ticket_id, unreachable


def _capturing_handler(capture: dict[str, Any], *, status: int = 201) -> Handler:
    """Build a fake Ticket handler that records the forwarded request and returns a fixed response.

    Args:
        capture: A dict the handler fills with the received method, path, headers, body, and query.
        status: The status code to return.

    Returns:
        A mock-transport handler for the fake Ticket Service.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        """Record the request and return a canned created-ticket response.

        Args:
            request: The incoming request.

        Returns:
            A canned response echoing the recorded state.
        """
        capture["method"] = request.method
        capture["path"] = request.url.path
        capture["headers"] = dict(request.headers)
        capture["content"] = request.content.decode("utf-8")
        capture["query"] = dict(request.url.params)
        return httpx.Response(status, json={"id": "created"})

    return _handler


async def test_create_forwards_body_token_and_idempotency_key(build_client: ClientFactory) -> None:
    """Registration forwards the body, bearer token, idempotency key, and correlation ID."""
    capture: dict[str, Any] = {}
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:create",)),
        ticket_handler=_capturing_handler(capture, status=201),
    )
    response = await client.post(
        "/api/v1/tickets",
        json={"subject": "Test"},
        headers={"Authorization": "Bearer good", "Idempotency-Key": "abc-123"},
    )
    assert response.status_code == 201
    assert capture["method"] == "POST"
    assert capture["path"] == "/api/v1/tickets"
    assert capture["headers"]["authorization"] == "Bearer good"
    assert capture["headers"]["idempotency-key"] == "abc-123"
    assert '"subject"' in capture["content"]
    # The platform HTTP client propagates the correlation ID to downstream calls.
    assert "x-correlation-id" in capture["headers"]


async def test_search_forwards_query_parameters(build_client: ClientFactory) -> None:
    """Search forwards the query parameters to the Ticket Service."""
    capture: dict[str, Any] = {}
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_capturing_handler(capture, status=200),
    )
    response = await client.get(
        "/api/v1/tickets?statusCode=NEW&pageSize=10", headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 200
    assert capture["path"] == "/api/v1/tickets"
    assert capture["query"] == {"statusCode": "NEW", "pageSize": "10"}


async def test_reference_data_forwards_query_and_relays(build_client: ClientFactory) -> None:
    """Reference data forwards the types filter to the Ticket Service and relays its response."""
    capture: dict[str, Any] = {}
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_capturing_handler(capture, status=200),
    )
    response = await client.get(
        "/api/v1/reference-data?types=product,priority",
        headers={"Authorization": "Bearer good"},
    )
    assert response.status_code == 200
    assert capture["method"] == "GET"
    assert capture["path"] == "/api/v1/reference-data"
    assert capture["query"] == {"types": "product,priority"}


async def test_reference_data_denied_without_read_permission(build_client: ClientFactory) -> None:
    """A caller lacking ticket:read cannot read reference data; the gateway rejects it with 403."""
    capture: dict[str, Any] = {}
    client = await build_client(
        iam_handler=auth_me_handler(("iam:manage",)),
        ticket_handler=_capturing_handler(capture, status=200),
    )
    response = await client.get("/api/v1/reference-data", headers={"Authorization": "Bearer good"})
    assert response.status_code == 403
    # The gateway short-circuits before ever calling the Ticket Service.
    assert capture == {}


async def test_create_denied_without_permission(build_client: ClientFactory) -> None:
    """A read-only caller cannot register an appeal; the gateway rejects it with 403."""
    capture: dict[str, Any] = {}
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_capturing_handler(capture, status=201),
    )
    response = await client.post(
        "/api/v1/tickets", json={"subject": "Test"}, headers={"Authorization": "Bearer good"}
    )
    assert response.status_code == 403
    # The gateway short-circuits before ever calling the Ticket Service.
    assert capture == {}


async def test_downstream_client_error_status_preserved_text_not_leaked(
    build_client: ClientFactory,
) -> None:
    """A downstream 422 keeps its status but its free-form title/detail text is not relayed."""

    def _ticket_handler(request: httpx.Request) -> httpx.Response:
        """Return a 422 whose title/detail contain internal diagnostic text.

        Args:
            request: The incoming request.

        Returns:
            A 422 Problem Details response with sensitive text.
        """
        return httpx.Response(
            422,
            content=(
                b'{"title":"SQL validation failed at db.internal",'
                b'"detail":"OperationalError at http://db.internal:5432","status":422}'
            ),
            headers={"content-type": "application/problem+json"},
        )

    client = await build_client(
        iam_handler=auth_me_handler(("ticket:update",)),
        ticket_handler=_ticket_handler,
    )
    ticket_id = new_ticket_id()
    response = await client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"subject": ""},
        headers={"Authorization": "Bearer good"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    # The gateway substitutes a safe status-derived title and drops the downstream text.
    body = response.json()
    assert body["title"] == "Unprocessable entity"
    assert "db.internal" not in response.text
    assert "OperationalError" not in response.text
    assert "SQL" not in response.text


async def test_maps_ticket_outage_to_503(build_client: ClientFactory) -> None:
    """An unreachable Ticket Service surfaces as a gateway 503 on a forwarded command."""
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:comment",)),
        ticket_handler=unreachable,
    )
    ticket_id = new_ticket_id()
    response = await client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        json={"body": "hi"},
        headers={"Authorization": "Bearer good"},
    )
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_downstream_5xx_html_body_is_not_leaked(build_client: ClientFactory) -> None:
    """A downstream HTML 500 with internal details is normalized to a safe 502, body not relayed."""

    def _ticket_handler(request: httpx.Request) -> httpx.Response:
        """Return an HTML 500 containing internal details.

        Args:
            request: The incoming request.

        Returns:
            A 500 HTML response.
        """
        return httpx.Response(
            500,
            content=b"<html>OperationalError at db-internal.corp:5432 SELECT * FROM ticket</html>",
            headers={"content-type": "text/html"},
        )

    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)), ticket_handler=_ticket_handler
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")
    # None of the internal details cross the boundary.
    assert "db-internal" not in response.text
    assert "OperationalError" not in response.text
    assert "SELECT" not in response.text


async def test_semantic_headers_are_propagated(build_client: ClientFactory) -> None:
    """A downstream 429 Retry-After is preserved; non-allowlisted headers are dropped."""

    def _ticket_handler(request: httpx.Request) -> httpx.Response:
        """Return a 429 Problem Details with a Retry-After and an internal header.

        Args:
            request: The incoming request.

        Returns:
            A 429 response.
        """
        return httpx.Response(
            429,
            content=b'{"title":"Too many requests","status":429}',
            headers={
                "content-type": "application/problem+json",
                "retry-after": "30",
                "x-internal-node": "worker-7",
            },
        )

    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)), ticket_handler=_ticket_handler
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert "x-internal-node" not in response.headers


async def test_missing_token_challenges_with_www_authenticate(build_client: ClientFactory) -> None:
    """A gateway 401 for a missing token carries the standard Bearer challenge (LOW-001)."""
    client = await build_client(iam_handler=auth_me_handler(("ticket:read",)))
    response = await client.get("/api/v1/tickets")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"

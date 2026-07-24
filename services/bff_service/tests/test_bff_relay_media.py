"""Exact JSON media-type enforcement on the ordinary relay and auth-context trust boundaries.

The workspace already used exact media-type matching; this proves the ordinary Ticket relay and the
IAM auth-context path apply the same fail-closed policy, so a downstream ``application/jsonp`` or
``text/application/json`` success is rejected as a safe ``502`` and its body never leaks
(CR-BFF-R6-MEDIUM-003).
"""

from __future__ import annotations

import httpx
import pytest
from bff_fakes import ClientFactory, Handler, auth_me_handler

_SECRET = "db-internal.corp:5432"


def _ticket_media_handler(*, body: bytes, content_type: str | None, status: int = 200) -> Handler:
    """Build a Ticket handler returning a chosen body, media type and status for the search read.

    Args:
        body: The raw response body.
        content_type: The response ``Content-Type`` header, or ``None`` to omit it.
        status: The response status code.

    Returns:
        A mock-transport handler.
    """
    headers = {"content-type": content_type} if content_type is not None else {}

    def _handler(request: httpx.Request) -> httpx.Response:
        """Return the configured response for the search read.

        Args:
            request: The incoming request.

        Returns:
            The configured response.
        """
        return httpx.Response(status, content=body, headers=headers)

    return _handler


def _iam_auth_me_media(*, content_type: str | None) -> Handler:
    """Build an IAM handler whose ``/auth/me`` returns a subject body under a given media type.

    Args:
        content_type: The ``Content-Type`` header for the identity response, or ``None`` to omit it.

    Returns:
        A mock-transport handler.
    """
    body = (
        b'{"subject":"018f9a3c-0000-7000-8000-000000000001","username":"t",'
        b'"roles":["EMPLOYEE"],"permissions":["ticket:read"]}'
    )
    headers = {"content-type": content_type} if content_type is not None else {}

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve ``/auth/me`` with the configured media type.

        Args:
            request: The incoming request.

        Returns:
            The identity response, or 404 for other paths.
        """
        if request.url.path == "/api/v1/auth/me":
            return httpx.Response(200, content=body, headers=headers)
        return httpx.Response(404, json={"title": "Not found", "status": 404})

    return _handler


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "Application/JSON"],
)
async def test_ordinary_relay_accepts_exact_json(
    build_client: ClientFactory, content_type: str
) -> None:
    """An exact JSON media type (with parameters/casing) is relayed as a 200."""
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_media_handler(
            body=b'{"items":[],"page":{"page":1,"pageSize":20,"total":0}}',
            content_type=content_type,
        ),
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "content_type",
    ["application/jsonp", "text/application/json", None, "text/plain"],
)
async def test_ordinary_relay_rejects_near_miss_media(
    build_client: ClientFactory, content_type: str | None
) -> None:
    """A near-miss or missing media type on a 2xx is a safe 502 and the body does not leak."""
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_media_handler(
            body=b'{"secret":"' + _SECRET.encode() + b'"}', content_type=content_type
        ),
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")
    assert _SECRET not in response.text


async def test_ordinary_relay_rejects_malformed_json(build_client: ClientFactory) -> None:
    """A correct media type with a malformed body is a safe 502 that does not leak the body."""
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_media_handler(
            body=b"not json " + _SECRET.encode(), content_type="application/json"
        ),
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 502
    assert _SECRET not in response.text


async def test_ordinary_relay_rejects_oversized_downstream_response(
    build_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A downstream 2xx body over the egress ceiling is a safe 502, not a buffered relay."""
    monkeypatch.setenv("BFF_MAX_RESPONSE_BYTES", "500")
    client = await build_client(
        iam_handler=auth_me_handler(("ticket:read",)),
        ticket_handler=_ticket_media_handler(
            body=b'{"x":"' + b"a" * 2_000 + b'"}', content_type="application/json"
        ),
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=utf-8", "Application/JSON"],
)
async def test_auth_context_accepts_exact_json(
    build_client: ClientFactory, content_type: str
) -> None:
    """The auth-context path accepts an exact JSON identity response (with parameters/casing)."""
    client = await build_client(
        iam_handler=_iam_auth_me_media(content_type=content_type),
        ticket_handler=lambda request: httpx.Response(
            200, json={"items": [], "page": {"page": 1, "pageSize": 20, "total": 0}}
        ),
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "content_type",
    ["application/jsonp", "text/application/json", None],
)
async def test_auth_context_rejects_near_miss_media(
    build_client: ClientFactory, content_type: str | None
) -> None:
    """A near-miss identity media type is not trusted; the gateway returns a safe 502."""
    client = await build_client(
        iam_handler=_iam_auth_me_media(content_type=content_type),
        ticket_handler=lambda request: httpx.Response(200, json={"items": []}),
    )
    response = await client.get("/api/v1/tickets", headers={"Authorization": "Bearer good"})
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")

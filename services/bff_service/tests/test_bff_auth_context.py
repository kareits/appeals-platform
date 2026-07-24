"""Auth-context and login-proxy tests for the BFF gateway."""

from __future__ import annotations

import httpx
from bff_fakes import ClientFactory, auth_me_handler, auth_me_unauthorized, unreachable


def _iam_malformed_200(request: httpx.Request) -> httpx.Response:
    """Fake IAM handler returning a 200 with a non-JSON body for ``/auth/me``.

    Args:
        request: The incoming request.

    Returns:
        A 200 HTML response for ``/auth/me``, otherwise 404.
    """
    if request.url.path == "/api/v1/auth/me":
        return httpx.Response(
            200, content=b"<html>not json</html>", headers={"content-type": "text/html"}
        )
    return httpx.Response(404, json={"title": "Not found", "status": 404})


async def test_auth_me_returns_resolved_context(build_client: ClientFactory) -> None:
    """A valid bearer token resolves to the subject's roles and permissions via IAM."""
    client = await build_client(iam_handler=auth_me_handler(("ticket:read", "ticket:create")))
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "tester"
    assert body["roles"] == ["EMPLOYEE"]
    assert set(body["permissions"]) == {"ticket:read", "ticket:create"}


async def test_auth_me_without_token_is_unauthorized(build_client: ClientFactory) -> None:
    """A missing bearer token is rejected at the gateway before any upstream call."""
    client = await build_client(iam_handler=auth_me_handler(("ticket:read",)))
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_auth_me_relays_iam_rejection(build_client: ClientFactory) -> None:
    """An IAM 401 for a presented token surfaces as a gateway 401."""
    client = await build_client(iam_handler=auth_me_unauthorized)
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer stale"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_auth_me_maps_iam_outage_to_503(build_client: ClientFactory) -> None:
    """An unreachable IAM service surfaces as a gateway 503, not a 500."""
    client = await build_client(iam_handler=unreachable)
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer good"})
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_auth_me_malformed_iam_success_maps_to_502(build_client: ClientFactory) -> None:
    """A malformed IAM 200 (non-JSON) becomes a safe gateway 502, not an unhandled 500."""
    client = await build_client(iam_handler=_iam_malformed_200)
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer good"})
    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_login_relays_iam_token(build_client: ClientFactory) -> None:
    """The public login proxy relays the IAM token document verbatim."""
    client = await build_client(iam_handler=auth_me_handler(("ticket:read",)))
    response = await client.post(
        "/api/v1/auth/login", json={"username": "tester", "password": "changeme-dev-01"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accessToken"] == "signed.jwt.token"
    assert body["tokenType"] == "Bearer"

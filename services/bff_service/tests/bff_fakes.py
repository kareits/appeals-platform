"""Fake IAM/Ticket upstreams and shared types for BFF-service tests.

Kept in a uniquely named module (not ``conftest``) so test modules can import the handler builders
and type aliases without relying on cross-directory ``conftest`` importability. Provides
``httpx.MockTransport`` handlers that stand in for the IAM and Ticket services.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import httpx

# Fixed identifiers used across tests; never real credentials.
SUBJECT_ID = "018f9a3c-0000-7000-8000-000000000001"
IAM_BASE_URL = "http://iam.test"
TICKET_BASE_URL = "http://ticket.test"

Handler = Callable[[httpx.Request], httpx.Response]
ClientFactory = Callable[..., Awaitable[httpx.AsyncClient]]


def reject_all(request: httpx.Request) -> httpx.Response:
    """Default upstream handler that rejects every call with 404.

    Args:
        request: The incoming request.

    Returns:
        A 404 response.
    """
    return httpx.Response(404, json={"title": "Not found", "status": 404})


def unreachable(request: httpx.Request) -> httpx.Response:
    """Upstream handler that simulates a transport failure.

    Args:
        request: The incoming request.

    Returns:
        Never returns.

    Raises:
        httpx.ConnectError: Always, to simulate an unreachable upstream.
    """
    raise httpx.ConnectError("connection refused", request=request)


def auth_me_unauthorized(request: httpx.Request) -> httpx.Response:
    """Fake IAM handler that rejects ``/auth/me`` with 401 even when a token is presented.

    Args:
        request: The incoming request.

    Returns:
        A 401 response for ``/auth/me``, otherwise 404.
    """
    if request.url.path == "/api/v1/auth/me":
        return httpx.Response(401, json={"title": "Invalid token", "status": 401})
    return reject_all(request)


def auth_me_handler(
    permissions: tuple[str, ...],
    *,
    roles: tuple[str, ...] = ("EMPLOYEE",),
    subject: str = SUBJECT_ID,
    username: str = "tester",
) -> Handler:
    """Build a fake IAM handler that resolves ``/auth/me`` and proxies ``/auth/login``.

    ``/auth/me`` returns 401 without a bearer token and otherwise returns a subject document with
    the given roles and permissions; ``/auth/login`` returns a token document.

    Args:
        permissions: The permission claim strings the subject holds.
        roles: The role names the subject holds.
        subject: The subject identifier.
        username: The subject's login handle.

    Returns:
        A mock-transport handler for the fake IAM service.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve the fake IAM endpoints.

        Args:
            request: The incoming request.

        Returns:
            The simulated IAM response.
        """
        if request.url.path == "/api/v1/auth/me":
            if not request.headers.get("Authorization"):
                return httpx.Response(401, json={"title": "Not authenticated", "status": 401})
            return httpx.Response(
                200,
                json={
                    "subject": subject,
                    "username": username,
                    "roles": list(roles),
                    "permissions": list(permissions),
                },
            )
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                json={
                    "accessToken": "signed.jwt.token",
                    "tokenType": "Bearer",
                    "expiresIn": 3600,
                    "subject": subject,
                    "username": username,
                    "roles": list(roles),
                    "permissions": list(permissions),
                },
            )
        return reject_all(request)

    return _handler


def new_ticket_id() -> uuid.UUID:
    """Return a fresh ticket identifier for tests.

    Returns:
        A random UUID.
    """
    return uuid.uuid4()

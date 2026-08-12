"""Authentication and authorization tests for the document API.

The document service is a security boundary in its own right: it serves file bytes and must refuse
an unauthenticated or under-privileged caller even when reached directly, without the BFF
(CR-BFF-BLOCKER-001 precedent).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import jwt
import pytest
from httpx import AsyncClient

# The claim strings the document service enforces (see document_service.domain.permissions).
READ_PERMISSION = "ticket:read"
WRITE_PERMISSION = "ticket:update"

_FILE = {"file": ("statement.pdf", b"%PDF-1.4 content", "application/pdf")}

# Every document operation, as (method, path, needs-write) triples.
_OPERATIONS = (
    ("post", "/api/v1/documents", True),
    ("get", "/api/v1/documents", False),
    ("get", "/api/v1/documents/{documentId}", False),
    ("get", "/api/v1/documents/{documentId}/content", False),
    ("post", "/api/v1/documents/{documentId}/link", True),
)


def _request_kwargs(method: str, path: str) -> dict[str, object]:
    """Build the body/query arguments a given operation needs.

    Args:
        method: The HTTP method.
        path: The operation path.

    Returns:
        Keyword arguments for the HTTP client call.
    """
    if path.endswith("/link"):
        return {"json": {"ticketId": str(uuid.uuid4())}}
    if method == "post":
        return {"files": _FILE}
    if path == "/api/v1/documents":
        return {"params": {"ticketId": str(uuid.uuid4())}}
    return {}


@pytest.mark.parametrize(("method", "path", "_needs_write"), _OPERATIONS)
async def test_operations_require_authentication(
    unauth_client: AsyncClient, method: str, path: str, _needs_write: bool
) -> None:
    """No document operation is reachable without a bearer token."""
    url = path.format(documentId=uuid.uuid4())

    response = await unauth_client.request(method, url, **_request_kwargs(method, path))  # type: ignore[arg-type]

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "token_overrides",
    [
        pytest.param({"secret": "another-secret"}, id="wrong-signature"),
        pytest.param({"expired": True}, id="expired"),
        pytest.param({"issuer": "someone-else"}, id="wrong-issuer"),
        pytest.param({"audience": "another-audience"}, id="wrong-audience"),
    ],
)
async def test_invalid_tokens_are_refused(
    unauth_client: AsyncClient,
    make_token: Callable[..., str],
    token_overrides: dict[str, object],
) -> None:
    """A token that fails any verification step is rejected with 401."""
    token = make_token(**token_overrides)

    response = await unauth_client.get(
        "/api/v1/documents",
        params={"ticketId": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


async def test_unsigned_token_is_refused(unauth_client: AsyncClient) -> None:
    """An ``alg=none`` token is rejected by the fixed algorithm allowlist."""
    forged = jwt.encode(
        {
            "iss": "mfo-iam",
            "aud": "mfo-appeals",
            "sub": str(uuid.uuid4()),
            "username": "attacker",
            "roles": ["ADMIN"],
            "permissions": [READ_PERMISSION, WRITE_PERMISSION],
            "teams": [],
            "exp": 4102444800,
        },
        key="",
        algorithm="none",
    )

    response = await unauth_client.get(
        "/api/v1/documents",
        params={"ticketId": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


async def test_read_only_caller_cannot_upload_or_link(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A first-line read-only caller may read documents but never add or attach one."""
    header = {
        "Authorization": (
            f"Bearer {make_token(roles=('FIRST_LINE_READONLY',), permissions=(READ_PERMISSION,))}"
        )
    }

    listed = await unauth_client.get(
        "/api/v1/documents", params={"ticketId": str(uuid.uuid4())}, headers=header
    )
    uploaded = await unauth_client.post("/api/v1/documents", files=_FILE, headers=header)
    linked = await unauth_client.post(
        f"/api/v1/documents/{uuid.uuid4()}/link",
        json={"ticketId": str(uuid.uuid4())},
        headers=header,
    )

    assert listed.status_code == 200
    assert uploaded.status_code == 403
    assert linked.status_code == 403


async def test_caller_without_appeal_permissions_is_denied(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An administrator with no appeal permissions gets no document access either."""
    token = make_token(roles=("ADMIN",), permissions=("iam:manage",))
    header = {"Authorization": f"Bearer {token}"}

    response = await unauth_client.get(
        "/api/v1/documents", params={"ticketId": str(uuid.uuid4())}, headers=header
    )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_uploader_is_taken_from_the_token_not_the_request(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """``createdBy`` is the verified subject; a client cannot claim to be someone else."""
    subject = uuid.uuid4()
    header = {"Authorization": f"Bearer {make_token(subject=subject)}"}

    response = await unauth_client.post(
        "/api/v1/documents",
        files=_FILE,
        data={"createdBy": str(uuid.uuid4()), "ticketId": str(uuid.uuid4())},
        headers=header,
    )

    assert response.status_code == 201
    assert response.json()["createdBy"] == str(subject)

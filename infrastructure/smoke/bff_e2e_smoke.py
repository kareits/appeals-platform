"""Authenticated end-to-end smoke check for the BFF/IAM/Ticket stack.

Run against the reverse proxy (which publishes only the BFF). It exercises the real trust boundary
across services — not mocks — so the compose smoke fails unless an authenticated workflow succeeds
and the key security negatives hold (CR-BFF-MEDIUM-003):

- an employee can log in, register an appeal, and read its workspace;
- an ADMIN (no ticket permission) is denied registration with 403;
- a first-line read-only user is denied a mutation with 403;
- idempotency is scoped per caller: a second user replaying another user's key gets their own new
  appeal (no cross-user disclosure), and reusing a key with a different payload is a 409
  (CR-BFF-RR-BLOCKER-001).

Uses only the standard library so it needs no dependencies in the CI runner.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid

_DEV_PASSWORD = "changeme-dev-01"


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    """Perform an HTTP request and return the status and decoded JSON body.

    Args:
        base_url: The proxy base URL.
        method: The HTTP method.
        path: The request path.
        token: Optional bearer token.
        body: Optional JSON body.
        headers: Optional extra request headers.

    Returns:
        A tuple of the status code and the decoded JSON body (empty dict when not JSON).
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"{base_url}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    for name, value in (headers or {}).items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, _decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _decode(error.read())


def _decode(raw: bytes) -> dict:
    """Decode a JSON response body, tolerating an empty/non-JSON body.

    Args:
        raw: The raw response bytes.

    Returns:
        The decoded object, or an empty dict.
    """
    try:
        value = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _login(base_url: str, username: str) -> str:
    """Log in through the BFF and return the access token.

    Args:
        base_url: The proxy base URL.
        username: The dev username.

    Returns:
        The access token.

    Raises:
        AssertionError: If login does not return a token.
    """
    status, body = _request(
        base_url,
        "POST",
        "/api/v1/auth/login",
        body={"username": username, "password": _DEV_PASSWORD},
    )
    assert status == 200, f"login {username}: expected 200, got {status} {body}"
    token = body.get("accessToken")
    assert isinstance(token, str) and token, f"login {username}: no access token"
    return token


def _create_body() -> dict:
    """Return a minimal appeal-registration body.

    Returns:
        The request body.
    """
    return {
        "receivedAt": "2026-07-23T09:00:00Z",
        "sourceChannelCode": "EMAIL",
        "subject": "E2E smoke appeal",
        "description": "Created by the compose E2E smoke.",
        "productCode": "MICROLOAN",
        "classifierCode": "RESTRUCTURING",
        "priorityCode": "NORMAL",
        "applicant": {"applicantType": "CONSUMER", "dataSource": "MANUAL", "fullName": "E2E"},
    }


def _check_cross_user_idempotency(base_url: str, employee: str, supervisor: str) -> None:
    """Assert that idempotency is scoped per caller across the real service boundary.

    Reproduces the CR-BFF-RR-BLOCKER-001 IDOR through BFF -> IAM -> Ticket: a second user replaying
    another user's ``Idempotency-Key`` must receive their own new appeal (never the first user's),
    and reusing a key with a different payload must be a 409 conflict. A fresh key per run keeps the
    check re-runnable within a single stack.

    Args:
        base_url: The proxy base URL.
        employee: A first caller's access token.
        supervisor: A second caller's access token (different subject).

    Raises:
        AssertionError: If the idempotency scope is violated.
    """
    key = {"Idempotency-Key": f"e2e-{uuid.uuid4()}"}
    status_a, first = _request(
        base_url, "POST", "/api/v1/tickets", token=employee, body=_create_body(), headers=key
    )
    assert status_a == 201, f"idempotency: employee create expected 201, got {status_a}"

    status_b, second = _request(
        base_url, "POST", "/api/v1/tickets", token=supervisor, body=_create_body(), headers=key
    )
    assert status_b == 201, f"idempotency: second-user create expected 201, got {status_b}"
    assert first["id"] != second["id"], "IDOR: a second user received another user's appeal"

    changed = dict(_create_body(), subject="A different subject")
    status_c, _ = _request(
        base_url, "POST", "/api/v1/tickets", token=employee, body=changed, headers=key
    )
    assert status_c == 409, (
        f"idempotency: reused key with changed body expected 409, got {status_c}"
    )


def main(base_url: str) -> int:
    """Run the authenticated E2E flow and security negatives.

    Args:
        base_url: The proxy base URL (for example, ``http://localhost:8080``).

    Returns:
        Process exit code (0 on success).
    """
    employee = _login(base_url, "employee")
    status, created = _request(
        base_url, "POST", "/api/v1/tickets", token=employee, body=_create_body()
    )
    assert status == 201, f"employee create: expected 201, got {status} {created}"
    ticket_id = created["id"]

    status, workspace = _request(
        base_url, "GET", f"/api/v1/tickets/{ticket_id}/workspace", token=employee
    )
    assert status == 200, f"workspace: expected 200, got {status}"
    assert workspace["sections"]["ticket"]["status"] == "ok", "workspace card not ok"

    admin = _login(base_url, "admin")
    status, _ = _request(base_url, "POST", "/api/v1/tickets", token=admin, body=_create_body())
    assert status == 403, f"admin create: expected 403 (no ticket permission), got {status}"

    firstline = _login(base_url, "firstline")
    status, _ = _request(
        base_url,
        "PATCH",
        f"/api/v1/tickets/{ticket_id}",
        token=firstline,
        body={"expectedVersion": 1, "subject": "hacked"},
    )
    assert status == 403, f"first-line mutation: expected 403, got {status}"

    supervisor = _login(base_url, "supervisor")
    _check_cross_user_idempotency(base_url, employee, supervisor)

    print(
        "BFF E2E smoke passed: login/create/workspace, ADMIN and first-line negatives, "
        "and per-caller idempotency (no cross-user disclosure)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"))

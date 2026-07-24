"""Security tests for the ticket service's independent authentication and authorization.

These reproduce the scenarios the independent review exploited (CR-BFF-BLOCKER-001): a direct call
with no token, forged actor identity, missing permission/scope, and IDOR. They assert the ticket
service enforces its own boundary even when reached directly, not only through the BFF.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from typing import Any

from httpx import AsyncClient

# Ticket permission claim sets per role, mirroring the IAM authorization matrix (the ticket subset).
_ROLE_PERMS: dict[str, tuple[str, ...]] = {
    "EMPLOYEE": (
        "ticket:read",
        "ticket:create",
        "ticket:update",
        "ticket:classify",
        "ticket:comment",
    ),
    "SUPERVISOR": (
        "ticket:read",
        "ticket:create",
        "ticket:update",
        "ticket:classify",
        "ticket:comment",
        "ticket:decide",
        "ticket:close",
        "ticket:legal_hold",
    ),
    "FIRST_LINE_READONLY": ("ticket:read",),
    "OMBUDSMAN": (
        "ticket:read",
        "ticket:comment",
        "ticket:decide",
        "ticket:close",
        "ticket:legal_hold",
    ),
    "ANALYST": ("ticket:read",),
    "AUDITOR": ("ticket:read",),
    "ADMIN": (),
}


def _create_body(**overrides: Any) -> dict[str, Any]:
    """Build a minimal camelCase create-ticket body.

    Args:
        **overrides: Top-level fields to override.

    Returns:
        The request body.
    """
    body: dict[str, Any] = {
        "receivedAt": "2026-07-22T09:00:00Z",
        "sourceChannelCode": "EMAIL",
        "subject": "Restructuring request",
        "description": "Full appeal text",
        "productCode": "MICROLOAN",
        "classifierCode": "RESTRUCTURING",
        "priorityCode": "NORMAL",
        "applicant": {
            "applicantType": "CONSUMER",
            "dataSource": "MANUAL",
            "fullName": "Иванов Иван",
            "identifierValue": "900101300123",
        },
    }
    body.update(overrides)
    return body


def _bearer(token: str) -> dict[str, str]:
    """Build an Authorization header for a token.

    Args:
        token: The access token.

    Returns:
        The header mapping.
    """
    return {"Authorization": f"Bearer {token}"}


def _role_token(
    make_token: Callable[..., str], role: str, *, subject: uuid.UUID, teams: tuple[str, ...] = ()
) -> str:
    """Mint a token for a role with that role's realistic permission set.

    Args:
        make_token: The token builder fixture.
        role: The role name.
        subject: The caller subject.
        teams: The caller's team identifier claims.

    Returns:
        The signed token.
    """
    return make_token(roles=(role,), permissions=_ROLE_PERMS[role], subject=subject, teams=teams)


async def _create_as(client: AsyncClient, token: str, **body_overrides: Any) -> dict[str, Any]:
    """Register a ticket as the holder of a token and return the created card.

    Args:
        client: The HTTP client.
        token: The caller's token.
        **body_overrides: Overrides for the create body.

    Returns:
        The created ticket card.
    """
    response = await client.post(
        "/api/v1/tickets", json=_create_body(**body_overrides), headers=_bearer(token)
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- Authentication (401) ---------------------------------------------------------------------


async def test_direct_read_without_token_is_401(unauth_client: AsyncClient) -> None:
    """A direct GET with no token is rejected 401 with a bearer challenge (the review's bypass)."""
    response = await unauth_client.get(f"/api/v1/tickets/{uuid.uuid4()}")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_direct_mutation_without_token_is_401(unauth_client: AsyncClient) -> None:
    """A direct comment POST with no token is rejected 401 (no unauthenticated write)."""
    response = await unauth_client.post(
        f"/api/v1/tickets/{uuid.uuid4()}/comments", json={"body": "x"}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_malformed_token_is_401(unauth_client: AsyncClient) -> None:
    """A non-JWT bearer value is rejected 401."""
    response = await unauth_client.get(
        f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer("not-a-jwt")
    )
    assert response.status_code == 401


async def test_expired_token_is_401(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An expired token is rejected 401."""
    response = await unauth_client.get(
        f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer(make_token(expired=True))
    )
    assert response.status_code == 401


async def test_wrong_issuer_is_401(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A token with the wrong issuer is rejected 401."""
    response = await unauth_client.get(
        f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer(make_token(issuer="evil-issuer"))
    )
    assert response.status_code == 401


async def test_wrong_audience_is_401(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A token with the wrong audience is rejected 401."""
    response = await unauth_client.get(
        f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer(make_token(audience="evil-aud"))
    )
    assert response.status_code == 401


async def test_wrong_secret_is_401(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A token signed with a different secret is rejected 401."""
    forged = make_token(secret="a-completely-different-secret-0123456789")
    response = await unauth_client.get(f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer(forged))
    assert response.status_code == 401


async def test_wrong_algorithm_is_401(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A token signed with an algorithm outside the allowlist is rejected 401."""
    # A 64-byte secret keeps PyJWT quiet about HS512 key length; the token is still rejected because
    # HS512 is not in the ticket service's allowlist.
    token = make_token(algorithm="HS512", secret="k" * 64)
    response = await unauth_client.get(f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer(token))
    assert response.status_code == 401


async def test_unsigned_alg_none_token_is_401(unauth_client: AsyncClient) -> None:
    """An unsigned ``alg=none`` token is rejected 401 (no algorithm confusion)."""

    def _b64(data: dict[str, Any]) -> str:
        """Base64url-encode a JWT segment without padding.

        Args:
            data: The segment payload.

        Returns:
            The encoded segment.
        """
        raw = json.dumps(data).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64(
        {
            "iss": "mfo-iam",
            "aud": "mfo-appeals",
            "sub": str(uuid.uuid4()),
            "username": "attacker",
            "roles": ["SUPERVISOR"],
            "permissions": ["ticket:read"],
            "teams": [],
            "exp": 9_999_999_999,
        }
    )
    unsigned = f"{header}.{payload}."
    response = await unauth_client.get(f"/api/v1/tickets/{uuid.uuid4()}", headers=_bearer(unsigned))
    assert response.status_code == 401


# --- Permission gate (403) --------------------------------------------------------------------


async def test_first_line_readonly_cannot_mutate(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A first-line read-only caller cannot mutate an appeal (regulatory; docs/01)."""
    author = uuid.uuid4()
    created = await _create_as(unauth_client, _role_token(make_token, "SUPERVISOR", subject=author))
    first_line = _role_token(make_token, "FIRST_LINE_READONLY", subject=uuid.uuid4())
    response = await unauth_client.patch(
        f"/api/v1/tickets/{created['id']}",
        json={"expectedVersion": 1, "subject": "Hacked"},
        headers=_bearer(first_line),
    )
    assert response.status_code == 403


async def test_admin_has_no_ticket_permissions(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An ADMIN token (identity admin only) cannot read appeals; ADMIN grants no ticket access."""
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    created = await _create_as(unauth_client, supervisor)
    admin = _role_token(make_token, "ADMIN", subject=uuid.uuid4())
    response = await unauth_client.get(f"/api/v1/tickets/{created['id']}", headers=_bearer(admin))
    assert response.status_code == 403


async def test_permission_missing_for_action_is_403(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An ANALYST (read-only) cannot add a comment (lacks ticket:comment)."""
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    created = await _create_as(unauth_client, supervisor)
    analyst = _role_token(make_token, "ANALYST", subject=uuid.uuid4())
    response = await unauth_client.post(
        f"/api/v1/tickets/{created['id']}/comments",
        json={"body": "note"},
        headers=_bearer(analyst),
    )
    assert response.status_code == 403


# --- Object/data scope and IDOR (403) ---------------------------------------------------------


async def test_employee_cannot_read_other_teams_ticket(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """Knowing a ticket UUID does not let an unrelated employee read it (IDOR closed)."""
    owner = uuid.uuid4()
    created = await _create_as(unauth_client, _role_token(make_token, "EMPLOYEE", subject=owner))
    other = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4(), teams=(str(uuid.uuid4()),))
    response = await unauth_client.get(f"/api/v1/tickets/{created['id']}", headers=_bearer(other))
    assert response.status_code == 403


async def test_employee_cannot_mutate_other_teams_ticket(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An unrelated employee cannot mutate another user's ticket by UUID."""
    owner = uuid.uuid4()
    created = await _create_as(unauth_client, _role_token(make_token, "EMPLOYEE", subject=owner))
    other = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    response = await unauth_client.patch(
        f"/api/v1/tickets/{created['id']}",
        json={"expectedVersion": 1, "subject": "Hacked"},
        headers=_bearer(other),
    )
    assert response.status_code == 403


async def test_registering_employee_can_read_their_own_ticket(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """The registering employee retains ownership-based read access to their appeal."""
    owner = uuid.uuid4()
    owner_token = _role_token(make_token, "EMPLOYEE", subject=owner)
    created = await _create_as(unauth_client, owner_token)
    response = await unauth_client.get(
        f"/api/v1/tickets/{created['id']}", headers=_bearer(owner_token)
    )
    assert response.status_code == 200


async def test_supervisor_reads_across_teams(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An oversight role (SUPERVISOR) may read an appeal registered by someone else."""
    created = await _create_as(
        unauth_client, _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    )
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    response = await unauth_client.get(
        f"/api/v1/tickets/{created['id']}", headers=_bearer(supervisor)
    )
    assert response.status_code == 200


# --- Confidentiality --------------------------------------------------------------------------


async def test_employee_cannot_create_confidential(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """An EMPLOYEE cannot register a confidential appeal it could not read back (R3-MEDIUM-001)."""
    employee = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    response = await unauth_client.post(
        "/api/v1/tickets",
        json=_create_body(isConfidential=True),
        headers=_bearer(employee),
    )
    assert response.status_code == 403


async def test_confidential_create_is_consistent_for_a_cleared_role(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A cleared creator sees a coherent create/replay/read outcome for a confidential appeal."""
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    created = await _create_as(unauth_client, supervisor, isConfidential=True)
    # The creator can read back what they registered (no 201-then-403 inconsistency).
    read = await unauth_client.get(f"/api/v1/tickets/{created['id']}", headers=_bearer(supervisor))
    assert read.status_code == 200
    assert read.json()["isConfidential"] is True
    # A non-cleared role is denied the confidential appeal.
    employee = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    denied = await unauth_client.get(f"/api/v1/tickets/{created['id']}", headers=_bearer(employee))
    assert denied.status_code == 403


async def test_confidential_replay_returns_original_for_creator(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A cleared creator's idempotent replay of a confidential create returns the original (200)."""
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    key = {"Idempotency-Key": f"conf-{uuid.uuid4()}"}
    first = await unauth_client.post(
        "/api/v1/tickets",
        json=_create_body(isConfidential=True),
        headers={**_bearer(supervisor), **key},
    )
    assert first.status_code == 201
    replay = await unauth_client.post(
        "/api/v1/tickets",
        json=_create_body(isConfidential=True),
        headers={**_bearer(supervisor), **key},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


# --- Trusted server-derived actor -------------------------------------------------------------


async def test_forged_author_id_is_rejected(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A client-supplied authorId is rejected (unknown field), closing forged-actor input."""
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    created = await _create_as(unauth_client, supervisor)
    response = await unauth_client.post(
        f"/api/v1/tickets/{created['id']}/comments",
        json={"body": "note", "authorId": str(uuid.uuid4())},
        headers=_bearer(supervisor),
    )
    assert response.status_code == 422


async def test_comment_author_is_the_caller_not_client_input(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """The stored comment author is the authenticated subject, not any client value."""
    subject = uuid.uuid4()
    token = _role_token(make_token, "SUPERVISOR", subject=subject)
    created = await _create_as(unauth_client, token)
    posted = await unauth_client.post(
        f"/api/v1/tickets/{created['id']}/comments", json={"body": "note"}, headers=_bearer(token)
    )
    assert posted.status_code == 201
    assert posted.json()["authorId"] == str(subject)


async def test_forged_decision_by_is_rejected(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A client-supplied decisionBy is rejected (unknown field)."""
    token = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    created = await _create_as(unauth_client, token)
    response = await unauth_client.post(
        f"/api/v1/tickets/{created['id']}/decision",
        json={
            "expectedVersion": 1,
            "decisionCode": "REJECTED",
            "decisionText": "x",
            "decisionBy": str(uuid.uuid4()),
        },
        headers=_bearer(token),
    )
    assert response.status_code == 422


def _combo_token(
    make_token: Callable[..., str], roles: tuple[str, ...], *, subject: uuid.UUID
) -> str:
    """Mint a token carrying multiple roles with the union of their permissions.

    Args:
        make_token: The token builder fixture.
        roles: The role names to combine.
        subject: The caller subject.

    Returns:
        The signed multi-role token.
    """
    permissions: set[str] = set()
    for role in roles:
        permissions.update(_ROLE_PERMS[role])
    return make_token(roles=roles, permissions=tuple(sorted(permissions)), subject=subject)


# --- Role composition must not escalate (CR-BFF-RR-HIGH-001) ------------------------------------


async def test_auditor_plus_employee_cannot_mutate_confidential(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """AUDITOR's confidential/global scope must not combine with EMPLOYEE's mutation permission."""
    supervisor = _role_token(make_token, "SUPERVISOR", subject=uuid.uuid4())
    created = await _create_as(unauth_client, supervisor, isConfidential=True)
    combo = _combo_token(make_token, ("AUDITOR", "EMPLOYEE"), subject=uuid.uuid4())

    mutated = await unauth_client.patch(
        f"/api/v1/tickets/{created['id']}",
        json={"expectedVersion": 1, "subject": "Tampered"},
        headers=_bearer(combo),
    )
    assert mutated.status_code == 403
    # The audit role may still observe the confidential ticket (read is allowed, mutation is not).
    read = await unauth_client.get(f"/api/v1/tickets/{created['id']}", headers=_bearer(combo))
    assert read.status_code == 200


async def test_auditor_plus_employee_cannot_mutate_other_team_ticket(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """AUDITOR's global read scope must not enable EMPLOYEE mutation of another team's ticket."""
    owner = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    created = await _create_as(unauth_client, owner)  # non-confidential, owned by another employee
    combo = _combo_token(make_token, ("AUDITOR", "EMPLOYEE"), subject=uuid.uuid4())

    mutated = await unauth_client.patch(
        f"/api/v1/tickets/{created['id']}",
        json={"expectedVersion": 1, "subject": "Tampered"},
        headers=_bearer(combo),
    )
    assert mutated.status_code == 403


# --- Idempotency is scoped per caller (CR-BFF-RR-BLOCKER-001) -----------------------------------


async def test_idempotency_key_is_scoped_per_caller(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A second user replaying another user's idempotency key gets their own ticket, not theirs."""
    user_a = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    user_b = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    key = {"Idempotency-Key": "shared-key"}

    created_a = await unauth_client.post(
        "/api/v1/tickets",
        json=_create_body(subject="Owner secret"),
        headers={**_bearer(user_a), **key},
    )
    assert created_a.status_code == 201
    id_a = created_a.json()["id"]

    replay_b = await unauth_client.post(
        "/api/v1/tickets", json=_create_body(subject="B body"), headers={**_bearer(user_b), **key}
    )
    # B must never receive A's appeal; B gets a distinct, newly created ticket.
    assert replay_b.status_code == 201
    assert replay_b.json()["id"] != id_a


async def test_same_caller_same_key_same_body_is_idempotent(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """A same-caller replay with the same key and body returns the original ticket (HTTP 200)."""
    token = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    key = {"Idempotency-Key": "same-key"}
    first = await unauth_client.post(
        "/api/v1/tickets", json=_create_body(), headers={**_bearer(token), **key}
    )
    second = await unauth_client.post(
        "/api/v1/tickets", json=_create_body(), headers={**_bearer(token), **key}
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_same_caller_same_key_different_body_is_conflict(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """Reusing a key with a different payload is a 409 conflict, not a silent replay."""
    token = _role_token(make_token, "EMPLOYEE", subject=uuid.uuid4())
    key = {"Idempotency-Key": "conflict-key"}
    first = await unauth_client.post(
        "/api/v1/tickets", json=_create_body(subject="Original"), headers={**_bearer(token), **key}
    )
    assert first.status_code == 201
    second = await unauth_client.post(
        "/api/v1/tickets", json=_create_body(subject="Changed"), headers={**_bearer(token), **key}
    )
    assert second.status_code == 409
    assert second.headers["content-type"].startswith("application/problem+json")


async def test_decision_actor_is_the_caller(
    unauth_client: AsyncClient, make_token: Callable[..., str]
) -> None:
    """The recorded decisionBy is the authenticated subject."""
    subject = uuid.uuid4()
    token = _role_token(make_token, "SUPERVISOR", subject=subject)
    created = await _create_as(unauth_client, token)
    response = await unauth_client.post(
        f"/api/v1/tickets/{created['id']}/decision",
        json={"expectedVersion": 1, "decisionCode": "REJECTED", "decisionText": "rationale"},
        headers=_bearer(token),
    )
    assert response.status_code == 200
    assert response.json()["decisionBy"] == str(subject)

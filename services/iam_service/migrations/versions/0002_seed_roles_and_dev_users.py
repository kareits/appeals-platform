"""Seed teams, dev/local users, and their role grants.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Immutable seed snapshot. This is a non-production dev/local dataset (docs/06): every seeded user
# shares the same well-known password so the platform is usable end-to-end before corporate OIDC
# (ADR-AUTH-OIDC, TASK_06). The bcrypt hashes below encode the password "changeme-dev-01" and are
# frozen here — regenerating them or changing the seed is a NEW migration, never an edit to this one
# (mirrors the ticket service's immutable-snapshot rule). Password hashes never expose the password.

# The seven role labels, mirrored from revision 0001's ``iam_role`` enum (kept as literals so the
# seed migration is self-contained; adding a role later is a new migration, never an edit here).
_ROLE_VALUES = (
    "EMPLOYEE",
    "SUPERVISOR",
    "FIRST_LINE_READONLY",
    "OMBUDSMAN",
    "ANALYST",
    "ADMIN",
    "AUDITOR",
)

_TEAM_FRONTLINE = "176d0d02-893b-407a-9b10-957c560392eb"
_TEAM_SECONDLINE = "b3f4c0d8-23c1-4a7f-a2ff-f870f09df2de"

_TEAMS = [
    {"id": _TEAM_FRONTLINE, "code": "FRONTLINE", "name": "First line"},
    {"id": _TEAM_SECONDLINE, "code": "SECONDLINE", "name": "Second line"},
]

# (user_id, username, full_name, team_id, bcrypt_hash, role_grant_id, role)
_USERS = [
    (
        "cd316ffe-cc51-4e3b-b7ca-a422bccf0f8d",
        "employee",
        "Dev Employee",
        _TEAM_SECONDLINE,
        "$2b$12$btn8nBWOSYMZ/qkDeA/F0.EW4kmkU88mTUcbrPmf9MW6nSwbjsZLu",
        "7d17c7a6-c006-44d1-868f-623f5997bbb9",
        "EMPLOYEE",
    ),
    (
        "cbf6d113-7b6d-4e30-b59a-7055814a70a0",
        "supervisor",
        "Dev Supervisor",
        _TEAM_SECONDLINE,
        "$2b$12$.QwHX.4exKb55hhfnMyqP.bLXYLtztAuEk/W3VKRYTQUFtRL79giK",
        "362a38aa-e9c2-4df2-aa5c-9b2a3b8c641c",
        "SUPERVISOR",
    ),
    (
        "792bf685-19e0-49c3-9a4a-0dfa8ffd8413",
        "firstline",
        "Dev First-line",
        _TEAM_FRONTLINE,
        "$2b$12$s0qdYppNNyC0FgyCERuZVOTO2BihEv176U.XX5HXpEoo4zRp.Hm16",
        "0d122a7e-091e-4f9b-9caa-e9246c02422b",
        "FIRST_LINE_READONLY",
    ),
    (
        "a3ce4749-c9bd-4a51-b760-bbad33702368",
        "ombudsman",
        "Dev Ombudsman",
        None,
        "$2b$12$kox6S3amQq/OOQPHEZdrmOTk4T8lxqwo6jhMm6kJa4YNX6UK1CubO",
        "b8672d7c-eb99-4c2d-8bd6-038b1051c599",
        "OMBUDSMAN",
    ),
    (
        "0a95e97e-d4ac-4e51-bb22-30273604cd7c",
        "analyst",
        "Dev Analyst",
        None,
        "$2b$12$kS8XY6SGd/Ema2y8ISwUOu9c2pbOteFujf8NMakcJUJ59wFFJ7KGy",
        "a3bd33ff-6f5b-4464-8976-988eb41de09a",
        "ANALYST",
    ),
    (
        "441f32c1-a736-4bd6-ac7f-244abc8802f3",
        "admin",
        "Dev Admin",
        None,
        "$2b$12$iGqaEarNjXm4iPyfFIi9ze8Z/3U6qIM.pn5KPC3EuIZtyPebw2HD.",
        "97fb1ee6-96e0-4b36-9332-7004f25435a1",
        "ADMIN",
    ),
    (
        "6aae0a04-8354-46f6-9f89-21b342cd1334",
        "auditor",
        "Dev Auditor",
        None,
        "$2b$12$t46o1A8NCzaDGs6eBdvDRO8U2dfm3ENDbbK6usRa89kmDfx.n9T6C",
        "fee5607a-812d-4c9f-b08a-32879adf2812",
        "AUDITOR",
    ),
]


def _team_table() -> sa.Table:
    """Return a lightweight table definition for bulk-inserting teams.

    Returns:
        The ``iam_team`` table with the columns the seed populates.
    """
    return sa.table(
        "iam_team",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
    )


def _user_table() -> sa.Table:
    """Return a lightweight table definition for bulk-inserting users.

    Returns:
        The ``iam_user`` table with the columns the seed populates.
    """
    return sa.table(
        "iam_user",
        sa.column("id", sa.Uuid()),
        sa.column("username", sa.String()),
        sa.column("full_name", sa.String()),
        sa.column("email", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("team_id", sa.Uuid()),
        sa.column("version", sa.Integer()),
    )


def _user_role_table() -> sa.Table:
    """Return a lightweight table definition for bulk-inserting role grants.

    Returns:
        The ``iam_user_role`` table with the columns the seed populates.
    """
    return sa.table(
        "iam_user_role",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        # Bind against the existing ``iam_role`` enum (created by revision 0001) with
        # ``create_type=False`` so PostgreSQL receives a properly typed enum value instead of a
        # VARCHAR cast (CR-IAM-BLOCKER-001). On SQLite the enum is a VARCHAR + CHECK, so this is
        # equivalent there. Re-declaring the type here keeps the seed migration self-contained.
        sa.column("role", sa.Enum(*_ROLE_VALUES, name="iam_role", create_type=False)),
    )


def upgrade() -> None:
    """Insert the dev/local teams, users, and role grants.

    Identifier literals are converted to ``uuid.UUID`` objects so the ``Uuid`` columns serialize
    them consistently across backends (SQLite stores them as hex).
    """
    op.bulk_insert(
        _team_table(),
        [
            {"id": uuid.UUID(team["id"]), "code": team["code"], "name": team["name"]}
            for team in _TEAMS
        ],
    )
    op.bulk_insert(
        _user_table(),
        [
            {
                "id": uuid.UUID(user_id),
                "username": username,
                "full_name": full_name,
                "email": f"{username}@example.test",
                "password_hash": password_hash,
                "is_active": True,
                "team_id": uuid.UUID(team_id) if team_id is not None else None,
                "version": 1,
            }
            for user_id, username, full_name, team_id, password_hash, _grant_id, _role in _USERS
        ],
    )
    op.bulk_insert(
        _user_role_table(),
        [
            {"id": uuid.UUID(grant_id), "user_id": uuid.UUID(user_id), "role": role}
            for user_id, _username, _full_name, _team_id, _hash, grant_id, role in _USERS
        ],
    )


def downgrade() -> None:
    """Remove the seeded role grants, users, and teams by their fixed identifiers.

    Only the exact seeded rows are deleted (by primary key), so any user or role created after
    seeding is left untouched and the identity/audit-protection guard on revision 0001 is respected.
    """
    user_roles = _user_role_table()
    users = _user_table()
    teams = _team_table()
    grant_ids = [uuid.UUID(grant_id) for *_rest, grant_id, _role in _USERS]
    user_ids = [uuid.UUID(user_id) for user_id, *_rest in _USERS]
    team_ids = [uuid.UUID(team["id"]) for team in _TEAMS]
    op.execute(user_roles.delete().where(user_roles.c.id.in_(grant_ids)))
    op.execute(users.delete().where(users.c.id.in_(user_ids)))
    op.execute(teams.delete().where(teams.c.id.in_(team_ids)))

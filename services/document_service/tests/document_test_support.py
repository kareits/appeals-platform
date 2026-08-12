"""Test helpers shared by document-service tests.

Lives in a uniquely named module (not in ``conftest.py``) because tests directories are not
packages, so a test module cannot import from ``conftest`` directly. The name is unique across the
repository to keep the flat test-module namespace collision-free, matching the existing
``pg_test_safety`` and ``bff_fakes`` precedent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from document_service.config import Settings
from document_service.domain.scope import AppealScopeDeniedError, AppealScopeUnavailableError
from document_service.infrastructure.models import Base
from sqlalchemy.ext.asyncio import create_async_engine

# Test signing material matching the document service's local defaults, so a minted token verifies.
TEST_JWT_SECRET = "dev-insecure-secret-change-me-please"
TEST_JWT_ISSUER = "mfo-iam"
TEST_JWT_AUDIENCE = "mfo-appeals"

# A default caller identity used across tests unless a test overrides it.
DEFAULT_SUBJECT = uuid.UUID("018f9a3c-0000-7000-8000-0000000000bb")

# The permission claims a document-handling caller holds. The document service authorizes on appeal
# permissions until dedicated ``document:*`` claims exist (see domain/permissions.py).
READ_PERMISSION = "ticket:read"
WRITE_PERMISSION = "ticket:update"
ALL_DOCUMENT_PERMISSIONS = (READ_PERMISSION, WRITE_PERMISSION)


def mint_token(
    *,
    subject: uuid.UUID = DEFAULT_SUBJECT,
    roles: tuple[str, ...] = ("SUPERVISOR",),
    permissions: tuple[str, ...] = ALL_DOCUMENT_PERMISSIONS,
    teams: tuple[str, ...] = (),
    username: str = "tester",
    secret: str = TEST_JWT_SECRET,
    algorithm: str = "HS256",
    issuer: str = TEST_JWT_ISSUER,
    audience: str = TEST_JWT_AUDIENCE,
    expired: bool = False,
) -> str:
    """Mint a signed access token with defaults and overrides.

    Args:
        subject: The subject claim.
        roles: The role-name claims.
        permissions: The permission claims.
        teams: The team identifier claims.
        username: The username claim.
        secret: The signing secret.
        algorithm: The signing algorithm.
        issuer: The ``iss`` claim.
        audience: The ``aud`` claim.
        expired: When true, issue an already-expired token.

    Returns:
        The encoded token.
    """
    now = datetime.now(UTC)
    exp = now - timedelta(minutes=1) if expired else now + timedelta(hours=1)
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": str(subject),
        "username": username,
        "roles": list(roles),
        "permissions": list(permissions),
        "teams": list(teams),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def auth_headers() -> dict[str, str]:
    """Return an Authorization header for the default fully permitted caller.

    Returns:
        A header mapping carrying a valid bearer token.
    """
    return {"Authorization": f"Bearer {mint_token()}"}


def build_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Build test settings backed by a temporary database and storage root.

    Args:
        tmp_path: Pytest-provided temporary directory.
        **overrides: Settings fields to override.

    Returns:
        The settings instance.
    """
    values: dict[str, object] = {
        "environment": "test",
        "database_url": f"sqlite+aiosqlite:///{tmp_path / 'documents.db'}",
        "storage_root": tmp_path / "storage",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class FakeScopeChecker:
    """An appeal-scope port stand-in that records calls and replays configured decisions.

    Tests need to exercise the document rules without a live Ticket Service and — more
    importantly — need to assert that the *right* decision is consulted, with the caller's own
    token, on every operation. Read and write are configured separately so a test can reproduce the
    composite-role case the Ticket Service really produces: readable but not mutable
    (CR-DOC-HIGH-002).

    Attributes:
        calls: Every ``(operation, ticket_id, access_token)`` triple asked about, in order, where
            the operation is ``"read"`` or ``"write"``.
    """

    def __init__(
        self,
        *,
        denied: set[uuid.UUID] | None = None,
        write_denied: set[uuid.UUID] | None = None,
        unavailable: bool = False,
        allow_all: bool = True,
    ) -> None:
        """Initialize the fake.

        Args:
            denied: Appeals the caller may not reach at all (both read and write are refused).
            write_denied: Appeals the caller may read but not modify — the composite-role case.
            unavailable: When true, every decision fails as unavailable (503).
            allow_all: When false, only appeals explicitly passed to :meth:`allow` are permitted.
        """
        self.calls: list[tuple[str, uuid.UUID, str]] = []
        self._denied = set(denied or ())
        self._write_denied = set(write_denied or ())
        self._unavailable = unavailable
        self._allow_all = allow_all
        self._allowed: set[uuid.UUID] = set()

    @property
    def read_calls(self) -> list[tuple[uuid.UUID, str]]:
        """Return the read decisions that were requested.

        Returns:
            The ``(ticket_id, access_token)`` pairs asked about for reading.
        """
        return [(ticket, token) for operation, ticket, token in self.calls if operation == "read"]

    @property
    def write_calls(self) -> list[tuple[uuid.UUID, str]]:
        """Return the write decisions that were requested.

        Returns:
            The ``(ticket_id, access_token)`` pairs asked about for writing.
        """
        return [(ticket, token) for operation, ticket, token in self.calls if operation == "write"]

    def allow(self, *ticket_ids: uuid.UUID) -> None:
        """Permit specific appeals when the fake is not in allow-all mode.

        Args:
            *ticket_ids: Appeals the caller may reach.
        """
        self._allowed.update(ticket_ids)

    def deny(self, *ticket_ids: uuid.UUID) -> None:
        """Start refusing specific appeals entirely, so a test can revoke access mid-scenario.

        Args:
            *ticket_ids: Appeals the caller may no longer reach.
        """
        self._denied.update(ticket_ids)

    def deny_write(self, *ticket_ids: uuid.UUID) -> None:
        """Start refusing *mutations* of specific appeals while still allowing reads.

        Args:
            *ticket_ids: Appeals the caller may read but not modify.
        """
        self._write_denied.update(ticket_ids)

    async def ensure_appeal_read_access(self, ticket_id: uuid.UUID, access_token: str) -> None:
        """Record the read question and replay the configured decision.

        Args:
            ticket_id: The appeal being checked.
            access_token: The caller's forwarded bearer token.

        Raises:
            AppealScopeUnavailableError: When configured to be unavailable.
            AppealScopeDeniedError: When the appeal is denied or not explicitly allowed.
        """
        self.calls.append(("read", ticket_id, access_token))
        self._decide(ticket_id)

    async def ensure_appeal_write_access(self, ticket_id: uuid.UUID, access_token: str) -> None:
        """Record the write question and replay the configured decision.

        Args:
            ticket_id: The appeal being checked.
            access_token: The caller's forwarded bearer token.

        Raises:
            AppealScopeUnavailableError: When configured to be unavailable.
            AppealScopeDeniedError: When the appeal is denied for reading or for mutation.
        """
        self.calls.append(("write", ticket_id, access_token))
        if ticket_id in self._write_denied:
            raise AppealScopeDeniedError("appeal mutation denied (fake)")
        self._decide(ticket_id)

    def _decide(self, ticket_id: uuid.UUID) -> None:
        """Apply the decisions shared by reads and writes.

        Args:
            ticket_id: The appeal being checked.

        Raises:
            AppealScopeUnavailableError: When configured to be unavailable.
            AppealScopeDeniedError: When the appeal is denied or not explicitly allowed.
        """
        if self._unavailable:
            raise AppealScopeUnavailableError("scope decision unavailable (fake)")
        if ticket_id in self._denied:
            raise AppealScopeDeniedError("appeal denied (fake)")
        if not self._allow_all and ticket_id not in self._allowed:
            raise AppealScopeDeniedError("appeal not allowed (fake)")


async def create_schema(database_url: str) -> None:
    """Create the document schema on a fresh database.

    Tests create the schema from the models rather than by running migrations; a dedicated
    migration test exercises the Alembic path.

    Args:
        database_url: The async database URL to initialize.
    """
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

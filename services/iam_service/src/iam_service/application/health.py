"""Application-level health checks for the IAM service."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DatabaseHealthCheck:
    """Health check that verifies database connectivity.

    Satisfies the ``mfo_observability.HealthCheck`` protocol (a ``name`` attribute and an async
    call returning a boolean).
    """

    name = "database"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the check.

        Args:
            session_factory: Factory used to open a database session.
        """
        self._session_factory = session_factory

    async def __call__(self) -> bool:
        """Run a trivial query to confirm the database is reachable.

        Returns:
            ``True`` if the query succeeds.
        """
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True


class SchemaHealthCheck:
    """Health check that verifies the IAM schema has been migrated.

    Connectivity alone is not readiness: a live process pointed at an un-migrated database would
    accept traffic and then fail every login with a missing-table error (CR-IAM-HIGH-001). This
    check queries a core owned table so readiness reflects a usable schema.
    """

    name = "schema"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the check.

        Args:
            session_factory: Factory used to open a database session.
        """
        self._session_factory = session_factory

    async def __call__(self) -> bool:
        """Confirm a core IAM table exists and is queryable.

        Returns:
            ``True`` if the ``iam_user`` table can be queried.
        """
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1 FROM iam_user LIMIT 1"))
        return True

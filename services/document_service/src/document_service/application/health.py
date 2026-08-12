"""Application-level health checks for the document service."""

from __future__ import annotations

import asyncio
from pathlib import Path

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


class StorageHealthCheck:
    """Health check that verifies the storage root is mounted and writable.

    Readiness has to cover storage, not just the database: with an unmounted or read-only volume the
    service can still answer metadata queries while every upload fails, which is exactly the state a
    load balancer must route away from.
    """

    name = "storage"

    def __init__(self, root: Path) -> None:
        """Initialize the check.

        Args:
            root: The configured storage root directory.
        """
        self._root = root

    def _probe(self) -> None:
        """Write and remove a probe file under the storage root.

        Raises:
            OSError: If the root is missing, unmounted, or not writable; the caller turns that into
                an unhealthy result.
        """
        probe = self._root / ".health-probe"
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)

    async def __call__(self) -> bool:
        """Verify that the storage root accepts a write.

        Returns:
            ``True`` when the storage root exists and accepts a write. A raised ``OSError`` is
            turned into an unhealthy result by the health-check runner.
        """
        await asyncio.to_thread(self._probe)
        return True

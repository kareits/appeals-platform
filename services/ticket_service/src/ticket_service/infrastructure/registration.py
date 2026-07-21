"""Allocation of unique business registration numbers.

The allocator hands out per-year monotonic sequence values from the ``registration_sequence``
counter table and formats them into a :class:`RegistrationNumber`. Uniqueness is enforced two ways:
the counter row is selected ``FOR UPDATE`` so concurrent allocations serialize (uniqueness
validation, TASK_01A), and the ``ticket.registration_number`` column carries a unique constraint as
a backstop. On SQLite (unit tests) ``FOR UPDATE`` is a no-op and write serialization provides the
same guarantee.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.domain.registration_number import RegistrationNumber
from ticket_service.infrastructure.models import RegistrationSequence


class RegistrationNumberAllocator:
    """Allocates unique, per-year business registration numbers.

    The allocator is stateless apart from its configured prefix; the durable counter lives in the
    database, so numbers stay unique across process restarts.
    """

    def __init__(self, prefix: str) -> None:
        """Initialize the allocator.

        Args:
            prefix: The uppercase deployment prefix embedded in every number (ADR-016).
        """
        self._prefix = prefix

    async def allocate(
        self, session: AsyncSession, *, at: datetime | None = None
    ) -> RegistrationNumber:
        """Allocate the next registration number for the year of ``at``.

        Reserves the next sequence value by locking (or creating) the counter row for the year and
        incrementing it. The caller commits the surrounding transaction; committing the ticket
        insert and the counter increment together keeps the number reserved even on rollback of
        unrelated work.

        Args:
            session: The active async session; its transaction owns the increment.
            at: The reference time whose year the number belongs to; defaults to the current UTC
                time.

        Returns:
            The freshly allocated, validated registration number.
        """
        moment = at or datetime.now(UTC)
        year = moment.year

        row = await session.get(RegistrationSequence, year, with_for_update=True)
        if row is None:
            row = RegistrationSequence(year=year, last_value=0)
            session.add(row)
            await session.flush()

        row.last_value += 1
        await session.flush()

        return RegistrationNumber.create(prefix=self._prefix, year=year, sequence=row.last_value)

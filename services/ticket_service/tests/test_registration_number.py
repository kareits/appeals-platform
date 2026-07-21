"""Tests for the registration-number value object and allocator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from ticket_service.domain.registration_number import RegistrationNumber
from ticket_service.infrastructure.registration import RegistrationNumberAllocator


def test_format_zero_pads_sequence() -> None:
    """The canonical form zero-pads the sequence to six digits."""
    number = RegistrationNumber.create(prefix="AP", year=2026, sequence=1)

    assert number.format() == "AP-2026-000001"
    assert str(number) == "AP-2026-000001"


def test_parse_round_trips() -> None:
    """Parsing a formatted number yields equal components and re-formats identically."""
    parsed = RegistrationNumber.parse("AP-2026-000042")

    assert parsed == RegistrationNumber.create(prefix="AP", year=2026, sequence=42)
    assert parsed.format() == "AP-2026-000042"


@pytest.mark.parametrize("value", ["", "AP-26-1", "ap-2026-000001", "AP/2026/1", "AP-2026-"])
def test_parse_rejects_invalid(value: str) -> None:
    """Malformed strings are rejected with a clear error."""
    with pytest.raises(ValueError):
        RegistrationNumber.parse(value)


@pytest.mark.parametrize(
    ("prefix", "year", "sequence"),
    [("ap", 2026, 1), ("AP", 26, 1), ("AP", 2026, 0), ("AP", 2026, -1)],
)
def test_construction_validates_components(prefix: str, year: int, sequence: int) -> None:
    """Invalid components are rejected at construction time."""
    with pytest.raises(ValueError):
        RegistrationNumber.create(prefix=prefix, year=year, sequence=sequence)


async def test_allocator_issues_unique_monotonic_numbers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sequential allocations within a year are unique and monotonically increasing."""
    allocator = RegistrationNumberAllocator(prefix="AP")
    at = datetime(2026, 3, 1, tzinfo=UTC)

    async with session_factory() as session:
        first = await allocator.allocate(session, at=at)
        second = await allocator.allocate(session, at=at)
        third = await allocator.allocate(session, at=at)
        await session.commit()

    numbers = [first.format(), second.format(), third.format()]
    assert numbers == ["AP-2026-000001", "AP-2026-000002", "AP-2026-000003"]
    assert len(set(numbers)) == 3


async def test_allocator_restarts_sequence_per_year(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Each calendar year has its own independent counter starting at one."""
    allocator = RegistrationNumberAllocator(prefix="AP")

    async with session_factory() as session:
        y2026 = await allocator.allocate(session, at=datetime(2026, 12, 31, tzinfo=UTC))
        y2027 = await allocator.allocate(session, at=datetime(2027, 1, 1, tzinfo=UTC))
        await session.commit()

    assert y2026.format() == "AP-2026-000001"
    assert y2027.format() == "AP-2027-000001"

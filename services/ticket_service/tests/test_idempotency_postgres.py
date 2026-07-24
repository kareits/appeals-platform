"""Real concurrent-PostgreSQL idempotency tests for manual ticket registration.

These tests exercise the concurrency-recovery path against a genuine PostgreSQL server with two
independent connections and transactions racing on the same scoped idempotency key — the unique
constraint and ``SELECT ... FOR UPDATE`` serialization that SQLite cannot faithfully reproduce
(CR-BFF-R4-MEDIUM-003). They are destructive, so they run only when opted in against a disposable
``*_test`` database (see :mod:`pg_test_safety`, CR-BFF-R6-MEDIUM-002), and each run confines its
tables to a unique disposable schema that is dropped on teardown — the shared ``public`` schema and
any application tables are never touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
import pytest_asyncio
from pg_test_safety import destructive_tests_enabled, require_safe_test_url, unique_schema_name
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from ticket_service.application.commands import CreateTicketCommand
from ticket_service.application.errors import IdempotencyConflictError
from ticket_service.application.use_cases import create_manual_ticket
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.models import (
    AuditLog,
    Base,
    DictionaryEntry,
    OutboxEvent,
    Ticket,
)
from ticket_service.infrastructure.reference_seed import SEED_ENTRIES
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

pytestmark = pytest.mark.skipif(
    not destructive_tests_enabled(),
    reason=(
        "destructive PostgreSQL tests are opt-in; set ALLOW_DESTRUCTIVE_DATABASE_TESTS=1 and "
        "TICKET_TEST_DATABASE_URL to a disposable *_test database"
    ),
)


@pytest_asyncio.fixture
async def pg_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide a session factory over a unique, disposable PostgreSQL schema.

    The target URL is validated fail-closed (a non-disposable database raises), a uniquely named
    schema is created and used as the connection ``search_path``, the schema-local tables are
    created and the reference dictionaries seeded, and only that schema is dropped on teardown —
    cleanup can never reach ``public`` or any application table (CR-BFF-R6-MEDIUM-002). Each session
    from the factory uses its own pooled connection, which is what makes two gathered coroutines
    genuinely concurrent.

    Yields:
        A session factory bound to the disposable schema.
    """
    url = require_safe_test_url()
    schema = unique_schema_name()

    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    await admin.dispose()

    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            insert(DictionaryEntry),
            [
                {
                    "dictionary_type": entry["dictionary_type"],
                    "code": entry["code"],
                    "display_name_ru": entry["display_name_ru"],
                    "display_name_kk": None,
                    "sort_order": entry["sort_order"],
                    "is_active": True,
                }
                for entry in SEED_ENTRIES
            ],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
        cleanup = create_async_engine(url)
        async with cleanup.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await cleanup.dispose()


async def _register(
    factory: async_sessionmaker[AsyncSession],
    command: CreateTicketCommand,
    caller: TicketClaims,
    barrier: asyncio.Barrier,
) -> bool:
    """Register a ticket in its own transaction, rendezvousing on a barrier before committing.

    Each call opens a distinct session (and thus a distinct connection). The barrier releases both
    callers only once both have opened their transaction and reached the same point, so neither has
    committed when the other begins the use case: the two registrations genuinely overlap and race
    on the shared idempotency key rather than being scheduled one-after-another.

    Args:
        factory: The session factory bound to the test database.
        command: The registration command.
        caller: The authenticated caller.
        barrier: The rendezvous both concurrent callers wait on before proceeding.

    Returns:
        ``True`` if this call created the ticket, ``False`` on an idempotent hit.
    """
    async with factory() as session:
        # Force real overlap: both transactions are open and past their idempotency lookup before
        # either is allowed to insert/commit, so the loser must take the unique-key recovery path.
        await session.execute(select(func.count()).select_from(Ticket))
        await barrier.wait()
        _, created = await create_manual_ticket(
            session, RegistrationNumberAllocator("AP"), command, caller
        )
        await session.commit()
        return created


async def _race_two(
    factory: async_sessionmaker[AsyncSession],
    caller: TicketClaims,
    first: CreateTicketCommand,
    second: CreateTicketCommand,
) -> list[Any]:
    """Run two registrations concurrently behind a shared barrier and return their outcomes.

    Args:
        factory: The session factory bound to the test database.
        caller: The authenticated caller shared by both registrations.
        first: The first registration command.
        second: The second registration command.

    Returns:
        A two-element list of either the ``created`` bool or the raised exception, in call order.
    """
    barrier = asyncio.Barrier(2)
    return list(
        await asyncio.gather(
            _register(factory, first, caller, barrier),
            _register(factory, second, caller, barrier),
            return_exceptions=True,
        )
    )


async def _count(factory: async_sessionmaker[AsyncSession], entity: type) -> int:
    """Return the row count of a mapped entity.

    Args:
        factory: The session factory bound to the test database.
        entity: The mapped ORM class to count.

    Returns:
        The number of rows.
    """
    async with factory() as session:
        return int((await session.execute(select(func.count()).select_from(entity))).scalar_one())


async def test_concurrent_same_payload_creates_one_ticket_event_and_audit(
    pg_session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Two concurrent creates with the same key and payload persist exactly one of everything."""
    caller = make_caller()
    command = make_create_command(idempotency_key="race-key")

    results = await _race_two(pg_session_factory, caller, command, command)

    # Neither call raised; exactly one created the ticket and the other recovered the winner.
    assert all(not isinstance(result, BaseException) for result in results), results
    assert sorted(results) == [False, True]
    assert await _count(pg_session_factory, Ticket) == 1
    assert await _count(pg_session_factory, OutboxEvent) == 1
    assert await _count(pg_session_factory, AuditLog) == 1


async def test_disposable_schema_cleanup_does_not_touch_public() -> None:
    """Dropping a disposable schema leaves objects in other schemas (here ``public``) untouched."""
    url = require_safe_test_url()
    marker = f"isolation_marker_{unique_schema_name().rsplit('_', 1)[-1]}"
    schema = unique_schema_name()

    engine = create_async_engine(url)
    try:
        # A sentinel table outside the disposable schema must survive its create/drop lifecycle.
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE TABLE public."{marker}" (id integer)'))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'CREATE TABLE "{schema}".scoped (id integer)'))
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        async with engine.connect() as connection:
            survived = await connection.execute(
                text("SELECT to_regclass(:name)"), {"name": f'public."{marker}"'}
            )
            assert survived.scalar_one() is not None
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP TABLE IF EXISTS public."{marker}"'))
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()


async def test_concurrent_same_key_different_payload_conflicts(
    pg_session_factory: async_sessionmaker[AsyncSession],
    make_create_command: Callable[..., CreateTicketCommand],
    make_caller: Callable[..., TicketClaims],
) -> None:
    """Two concurrent creates with the same key but different payloads yield one ticket and a 409.

    The winner commits its ticket; the loser's insert hits the unique idempotency constraint, and
    the recovery path re-checks the request fingerprint, which differs, so it raises a conflict
    rather than disclosing or duplicating the winner (CR-BFF-R5-MEDIUM-002).
    """
    caller = make_caller()
    first = make_create_command(idempotency_key="shared-key", subject="First subject")
    second = make_create_command(idempotency_key="shared-key", subject="Different subject")

    results = await _race_two(pg_session_factory, caller, first, second)

    successes = [result for result in results if result is True]
    conflicts = [result for result in results if isinstance(result, IdempotencyConflictError)]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results

    assert await _count(pg_session_factory, Ticket) == 1
    assert await _count(pg_session_factory, OutboxEvent) == 1
    assert await _count(pg_session_factory, AuditLog) == 1

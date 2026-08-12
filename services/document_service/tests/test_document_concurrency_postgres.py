"""Real-PostgreSQL tests for the write-once document-to-appeal link.

SQLite cannot reproduce the interesting behavior (its writes serialize at the file level), so the
guarantee that concurrent links cannot lose an update is verified against a genuine PostgreSQL
server (CR-DOC-MEDIUM-002).

The scenarios are **deterministic rather than timing-dependent**: simply gathering two coroutines
proves nothing, because whichever one acquires its connection first usually finishes before the
other reads, so the race never happens and the test would pass even against the defective
implementation. Instead, each test forces the exact interleaving it is about:

- ``test_stale_reader_cannot_move_the_link`` gives the second caller a snapshot taken **before** the
  first link commits — the state a read-then-write check evaluates — and asserts it gets a conflict
  instead of silently moving the evidence.
- ``test_second_writer_blocked_on_the_row_lock_gets_a_conflict`` holds the row lock in an
  uncommitted transaction, shows the competing statement blocking on it, and asserts that PostgreSQL
  re-evaluates the predicate once the lock is released, so no row matches.

The tests are destructive, so they run only when opted in against a disposable ``*_test`` database
(see :mod:`document_pg_safety`), and each run confines its tables to a unique schema that is dropped
on teardown — the shared ``public`` schema and any application table are never touched.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from document_pg_safety import destructive_tests_enabled, require_safe_test_url, unique_schema_name
from document_service.application.commands import Caller, LinkDocumentCommand
from document_service.application.errors import DocumentAlreadyLinkedError
from document_service.application.use_cases import link_document
from document_service.domain.enums import DocumentStatus
from document_service.infrastructure.models import Base, Document
from document_service.infrastructure.repositories import DocumentRepository
from document_test_support import DEFAULT_SUBJECT, FakeScopeChecker
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.skipif(
    not destructive_tests_enabled(),
    reason=(
        "destructive PostgreSQL tests are opt-in; set ALLOW_DESTRUCTIVE_DATABASE_TESTS=1 and "
        "DOCUMENT_TEST_DATABASE_URL to a disposable *_test database"
    ),
)

# How long the blocked-writer test waits to observe that the statement is really waiting on the
# row lock rather than having already completed.
_LOCK_WAIT_SECONDS = 0.5


@pytest_asyncio.fixture
async def pg_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide a session factory over a unique, disposable PostgreSQL schema.

    The target URL is validated fail-closed, a uniquely named schema is created and used as the
    connection ``search_path``, the schema-local tables are created, and only that schema is dropped
    on teardown. Each session from the factory uses its own pooled connection, so two sessions
    are genuinely independent transactions.

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
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
        cleanup = create_async_engine(url)
        async with cleanup.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await cleanup.dispose()


async def _insert_unlinked_document(
    factory: async_sessionmaker[AsyncSession], document_id: uuid.UUID
) -> None:
    """Insert one stored, unlinked document directly.

    Args:
        factory: The session factory bound to the disposable schema.
        document_id: The identifier to insert.
    """
    async with factory() as session:
        session.add(
            Document(
                id=document_id,
                ticket_id=None,
                message_id=None,
                original_filename="evidence.pdf",
                storage_backend="local",
                storage_key=f"2026/08/{uuid.uuid4().hex}",
                content_type="application/pdf",
                size_bytes=11,
                document_type_code=None,
                version=1,
                status=DocumentStatus.AVAILABLE,
                created_by=DEFAULT_SUBJECT,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _stored_ticket_id(
    factory: async_sessionmaker[AsyncSession], document_id: uuid.UUID
) -> uuid.UUID | None:
    """Read the persisted appeal linkage in a fresh transaction.

    Args:
        factory: The session factory bound to the disposable schema.
        document_id: The document to inspect.

    Returns:
        The stored appeal identifier, or ``None`` while unlinked.
    """
    async with factory() as session:
        return await session.scalar(select(Document.ticket_id).where(Document.id == document_id))


async def _link(
    session: AsyncSession, document_id: uuid.UUID, ticket_id: uuid.UUID
) -> uuid.UUID | None:
    """Run the link use case on a given session and report the resulting linkage.

    Args:
        session: The session (transaction) acting as this caller.
        document_id: The document to link.
        ticket_id: The appeal to link it to.

    Returns:
        The appeal the document ended up linked to, or ``None`` when the link was refused as a
        conflict.
    """
    try:
        document = await link_document(
            session,
            FakeScopeChecker(),
            LinkDocumentCommand(document_id=document_id, ticket_id=ticket_id, message_id=None),
            Caller(subject=DEFAULT_SUBJECT, access_token="test-token"),
        )
    except DocumentAlreadyLinkedError:
        return None
    return document.ticket_id


async def test_stale_reader_cannot_move_the_link(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A caller holding a pre-link snapshot gets a conflict instead of overwriting the linkage.

    This is the CR-DOC-MEDIUM-002 lost update, made deterministic: the second session reads the
    document while it is still unlinked (exactly what a read-then-write check evaluates), the
    first caller then links and commits, and only afterwards does the second caller attempt its
    link. A read-then-write implementation trusts its stale ``ticket_id IS NULL`` and moves the
    evidence; the conditional update re-evaluates the predicate in the database and matches no
    row.
    """
    document_id = uuid.uuid4()
    appeal_a = uuid.uuid4()
    appeal_b = uuid.uuid4()
    await _insert_unlinked_document(pg_session_factory, document_id)

    async with pg_session_factory() as session_b:
        # The stale snapshot: session B has the row in memory while it is still unlinked.
        stale = await DocumentRepository(session_b).get(document_id)
        assert stale is not None
        assert stale.ticket_id is None

        async with pg_session_factory() as session_a:
            assert await _link(session_a, document_id, appeal_a) == appeal_a

        assert await _link(session_b, document_id, appeal_b) is None

    assert await _stored_ticket_id(pg_session_factory, document_id) == appeal_a


async def test_second_writer_blocked_on_the_row_lock_gets_a_conflict(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A competing link waits on the row lock and then finds no matching row.

    Two genuinely concurrent transactions: the first holds an uncommitted link (and therefore the
    row lock), the second's statement blocks on it, and once the first commits PostgreSQL
    re-evaluates the conditional predicate against the new value — so the second link matches
    nothing and its caller is told it is a conflict rather than silently winning.
    """
    document_id = uuid.uuid4()
    appeal_a = uuid.uuid4()
    appeal_b = uuid.uuid4()
    await _insert_unlinked_document(pg_session_factory, document_id)

    async with pg_session_factory() as session_a, pg_session_factory() as session_b:
        repository_a = DocumentRepository(session_a)
        repository_b = DocumentRepository(session_b)

        assert await repository_a.link_to_ticket(document_id, appeal_a, None) is True

        competing = asyncio.create_task(repository_b.link_to_ticket(document_id, appeal_b, None))
        await asyncio.sleep(_LOCK_WAIT_SECONDS)
        assert not competing.done(), "the competing update did not wait on the row lock"

        await session_a.commit()

        assert await competing is False
        await session_b.commit()

    assert await _stored_ticket_id(pg_session_factory, document_id) == appeal_a


async def test_repeated_link_to_the_same_appeal_stays_idempotent(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Linking twice to the same appeal succeeds both times, rather than raising a conflict."""
    document_id = uuid.uuid4()
    appeal = uuid.uuid4()
    await _insert_unlinked_document(pg_session_factory, document_id)

    async with pg_session_factory() as first:
        assert await _link(first, document_id, appeal) == appeal
    async with pg_session_factory() as second:
        assert await _link(second, document_id, appeal) == appeal

    assert await _stored_ticket_id(pg_session_factory, document_id) == appeal

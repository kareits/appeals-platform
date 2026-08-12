"""Persistence repository for document metadata.

The repository encapsulates query construction so use cases stay free of SQL. It operates on the
caller's session and never commits; the surrounding unit of work owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import CursorResult, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from document_service.infrastructure.models import Document


class DocumentRepository:
    """Reads and writes document metadata."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active database session.
        """
        self._session = session

    def add(self, document: Document) -> None:
        """Stage a new document row for insertion.

        Args:
            document: The document metadata to add.
        """
        self._session.add(document)

    async def get(self, document_id: uuid.UUID) -> Document | None:
        """Load a document that has not been soft-deleted.

        Soft-deleted rows are excluded here rather than at every call site, so a deleted document is
        uniformly indistinguishable from a missing one (EP-4 introduces the deletion itself).

        Args:
            document_id: The document identifier.

        Returns:
            The document, or ``None`` when it is absent or soft-deleted.
        """
        result = await self._session.execute(
            select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def link_to_ticket(
        self, document_id: uuid.UUID, ticket_id: uuid.UUID, message_id: uuid.UUID | None
    ) -> bool:
        """Attach a document to an appeal atomically, refusing to move it away from another one.

        The write-once rule is expressed as the predicate of a single ``UPDATE``: the row is
        changed only while it is unlinked or already linked to the same appeal. Two concurrent links
        to different appeals therefore cannot both succeed — the second finds no matching row
        instead of overwriting the first writer's value, which a read-then-write check would allow
        (CR-DOC-MEDIUM-002). The statement does not commit; the caller owns the transaction.

        Args:
            document_id: The document to link.
            ticket_id: The appeal to link it to.
            message_id: The originating mail message to record, when supplied. ``None`` leaves any
                stored value untouched.

        Returns:
            ``True`` when the row was linked (or already carried this exact appeal), ``False`` when
            no row matched — the document is absent, soft-deleted, or belongs to another appeal.
        """
        values: dict[str, object] = {"ticket_id": ticket_id}
        if message_id is not None:
            values["message_id"] = message_id
        # ``CursorResult`` (which carries ``rowcount``) is the concrete type of a DML execution; the
        # generic ``execute`` signature returns ``Result``, so the narrowing is made explicit.
        result: CursorResult[Any] = await self._session.execute(  # type: ignore[assignment]
            update(Document)
            .where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
                or_(Document.ticket_id.is_(None), Document.ticket_id == ticket_id),
            )
            .values(**values)
            # The caller has usually loaded the same row already (the access check reads it), and
            # this session does not expire objects on commit; synchronizing keeps the in-memory
            # instance from being handed back with a stale ``ticket_id``.
            .execution_options(synchronize_session="fetch")
        )
        return bool(result.rowcount)

    async def list_for_ticket(
        self, ticket_id: uuid.UUID, *, page: int, page_size: int
    ) -> tuple[Sequence[Document], int]:
        """List an appeal's documents, newest first, together with the total count.

        Args:
            ticket_id: The appeal whose documents to list.
            page: 1-based page number.
            page_size: Maximum number of rows to return.

        Returns:
            A tuple of the page's documents and the total number of matching documents.
        """
        conditions = (Document.ticket_id == ticket_id, Document.deleted_at.is_(None))
        total = await self._session.scalar(
            select(func.count()).select_from(Document).where(*conditions)
        )
        result = await self._session.execute(
            select(Document)
            .where(*conditions)
            # ``id`` is a UUIDv7, so it breaks ties in creation order deterministically.
            .order_by(Document.created_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return result.scalars().all(), int(total or 0)

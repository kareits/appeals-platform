"""SQLAlchemy models owned by the document service.

The single table realizes the document-metadata dictionary (docs/02). It is the authoritative index
of everything on the storage volume: each row names the backend and the random storage key that
locates the bytes, plus the linkage other services rely on (``ticket_id`` and, for mail attachments,
``message_id``).

``ticket_id`` and ``message_id`` are deliberately plain UUID columns with **no** foreign key: the
appeals and mail messages they identify live in other services' databases, and a cross-service
database dependency is forbidden (root ``CLAUDE.md``, ADR-004). No column stores the content itself
— bytes belong on the storage backend, never in a database column or an event (docs/06).

The ``sha256`` and ``scan_status`` fields of the data dictionary arrive with TASK_03A-2 (hash and
antivirus), and versioning/soft-deletion behavior with EP-4; the ``version`` and ``deleted_at``
columns exist from the start so those phases add behavior rather than reshaping stored rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from document_service.domain.enums import DocumentStatus
from document_service.infrastructure.ids import uuid7

# Length caps for short coded values and filenames. Filenames are already truncated by the domain
# sanitizer; the column cap is the storage-level backstop.
_CODE_LEN = 64
_FILENAME_LEN = 255
_STORAGE_KEY_LEN = 128
_CONTENT_TYPE_LEN = 255


class Base(DeclarativeBase):
    """Declarative base for document-service ORM models."""


class Document(Base):
    """Metadata of a single stored document.

    Attributes:
        id: Internal UUIDv7 primary key; the identifier every other service and the frontend use.
        ticket_id: The appeal the document is linked to, or ``None`` while unlinked. Opaque here.
        message_id: The mail message the document arrived with, when applicable. Opaque here.
        original_filename: Sanitized client filename, kept for display only — the storage location
            is never derived from it (docs/06).
        storage_backend: Backend holding the bytes (``local`` in the MVP, ADR-014).
        storage_key: Random, unguessable key locating the object within that backend.
        content_type: Content type declared by the client at upload; recorded, not trusted. A
            validated allowlist arrives with TASK_03A-2.
        size_bytes: Number of bytes actually written to storage.
        document_type_code: Business document-type code, when the caller supplied one.
        version: Document version number; always 1 until EP-4 introduces versions.
        status: Storage lifecycle state; only ``AVAILABLE`` may be downloaded.
        created_by: The verified caller subject that uploaded the document (server-derived).
        created_at: Upload timestamp (UTC).
        deleted_at: Soft-deletion timestamp; set by EP-4, never by TASK_03A-1.
        migrated_at: When the object was migrated to another backend (ADR-014 dual-backend
            migration); unused until that job exists.
    """

    __tablename__ = "document"
    __table_args__ = (
        # Listing is always per appeal and newest first; the composite index serves that directly.
        Index("ix_document_ticket_id_created_at", "ticket_id", "created_at"),
        Index("ix_document_message_id", "message_id"),
        Index("ix_document_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)

    original_filename: Mapped[str] = mapped_column(String(_FILENAME_LEN))
    storage_backend: Mapped[str] = mapped_column(String(_CODE_LEN))
    # Unique: a key is generated randomly per upload, and the constraint turns the (astronomically
    # unlikely) collision or a buggy re-use into an insert failure instead of a silent overwrite.
    storage_key: Mapped[str] = mapped_column(String(_STORAGE_KEY_LEN), unique=True)
    content_type: Mapped[str] = mapped_column(String(_CONTENT_TYPE_LEN))
    size_bytes: Mapped[int] = mapped_column(Integer(), default=0)
    document_type_code: Mapped[str | None] = mapped_column(String(_CODE_LEN), nullable=True)

    version: Mapped[int] = mapped_column(Integer(), default=1)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=True)
    )

    created_by: Mapped[uuid.UUID] = mapped_column(Uuid())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    migrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

"""Document use cases: upload, retrieval, download, listing, and ticket linkage.

Business rules live here rather than in the FastAPI route handlers (root ``CLAUDE.md``).

**Authorization.** The API layer has already checked that the caller holds the required permission
claim. That is a coarse gate: it says the caller may work with appeal evidence *in general*, not
that they may reach *this* appeal. Every operation here therefore also demands a trusted
appeal-scope decision through :class:`~document_service.domain.scope.AppealScopeChecker` before any
metadata or byte is read, written, or linked (CR-DOC-HIGH-001).

Reads and writes ask **different** questions. Attaching or moving evidence changes an appeal's
record, so it requires a *mutation* decision, which Ticket scopes more narrowly than reading: an
audit role that may read across teams contributes no mutation scope, and its breadth must not
combine with another role's ``ticket:update`` permission (CR-DOC-HIGH-002). A document that is not
linked to an appeal yet has no appeal to decide on, so it stays visible to — and modifiable only
by — its uploader.

**Transaction boundaries.** Unlike a purely relational service, an upload spans two durable steps:
the metadata row is committed as ``UPLOADING`` *before* any byte is written, and updated to
``AVAILABLE`` (or ``UPLOAD_FAILED``) afterwards. That ordering is what keeps storage and metadata
reconcilable: an interrupted upload leaves a row that names its storage key — discoverable and never
downloadable — instead of an invisible orphan file on the volume. Because of that, the use cases in
this module own their commits; the route handlers do not commit.

**Content trust.** The declared filename and content type are untrusted: the filename is sanitized
and never used to build a storage path, and the content type is recorded for metadata only. Content
hashing, MIME allowlisting, and antivirus scanning arrive with TASK_03A-2.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from document_service.application.commands import (
    Caller,
    DocumentListQuery,
    LinkDocumentCommand,
    UploadDocumentCommand,
)
from document_service.application.errors import (
    DocumentAlreadyLinkedError,
    DocumentNotAvailableError,
    DocumentNotFoundError,
    StorageFailureError,
    UploadTooLargeError,
)
from document_service.domain.enums import DOWNLOADABLE_STATUSES, DocumentStatus
from document_service.domain.filenames import sanitize_filename
from document_service.domain.scope import AppealScopeChecker, AppealScopeDeniedError
from document_service.domain.storage import (
    FileStorage,
    StorageLimitExceededError,
    StoredObjectMissingError,
    generate_storage_key,
)
from document_service.infrastructure.ids import uuid7
from document_service.infrastructure.models import Document
from document_service.infrastructure.repositories import DocumentRepository

_logger = logging.getLogger(__name__)

# Recorded when the client declares no content type. The value is metadata only: downloads are
# always served as an untyped attachment (docs/06 — untrusted content is never rendered inline).
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# Cap on the recorded content type, matching the metadata column width.
_MAX_CONTENT_TYPE_LENGTH = 255


def _normalize_content_type(declared: str | None) -> str:
    """Reduce a declared content type to a bounded, single-line metadata value.

    The value is never used to decide how content is served, so normalization only has to keep it
    storable and safe to echo in logs and JSON: parameters (``; charset=…``) are dropped, control
    characters are removed, and the result is truncated and lowercased.

    Args:
        declared: The content type declared by the client, if any.

    Returns:
        The normalized content type, or :data:`DEFAULT_CONTENT_TYPE` when unusable.
    """
    if not declared:
        return DEFAULT_CONTENT_TYPE
    base = declared.split(";", 1)[0].strip().lower()
    cleaned = "".join(character for character in base if character.isprintable())
    return cleaned[:_MAX_CONTENT_TYPE_LENGTH] or DEFAULT_CONTENT_TYPE


async def _authorize_document(
    document: Document, caller: Caller, scope: AppealScopeChecker, *, for_write: bool = False
) -> None:
    """Authorize a caller against one stored document, failing closed.

    A linked document inherits its appeal's scope, decided by the Ticket Service (ADR-0008) — the
    read decision for a read, the narrower mutation decision when the document's record is about to
    change (CR-DOC-HIGH-002). An unlinked document has no appeal yet, so only the uploader may reach
    it — anything else would make a document readable by everyone during the window between upload
    and linking.

    Args:
        document: The document being accessed.
        caller: The authenticated caller.
        scope: The appeal-scope decision port.
        for_write: Whether the caller is about to modify the document's record rather than read it.

    Raises:
        AppealScopeDeniedError: The caller is outside the appeal's scope for this operation, or is
            not the uploader of an unlinked document.
        AppealScopeUnavailableError: No trusted decision could be obtained.
    """
    if document.ticket_id is None:
        if document.created_by != caller.subject:
            raise AppealScopeDeniedError("an unlinked document is visible only to its uploader")
        return
    if for_write:
        await scope.ensure_appeal_write_access(document.ticket_id, caller.access_token)
    else:
        await scope.ensure_appeal_read_access(document.ticket_id, caller.access_token)


async def upload_document(
    session: AsyncSession,
    storage: FileStorage,
    scope: AppealScopeChecker,
    command: UploadDocumentCommand,
    caller: Caller,
    *,
    max_upload_bytes: int,
) -> Document:
    """Store an uploaded file and record its metadata.

    When the upload names an appeal, the caller's right to **modify** it is decided before
    anything is written, so an unauthorized upload leaves neither metadata nor bytes behind. The
    metadata row is then committed as ``UPLOADING``, the content is streamed to the storage backend
    under a freshly generated random key, and the final size and an ``AVAILABLE`` status are
    committed. A failed
    write is committed as ``UPLOAD_FAILED``; the backend has already discarded the partial object,
    so no readable bytes survive a rejected upload.

    Args:
        session: The active database session; this function commits it.
        storage: The storage backend to write to.
        scope: The appeal-scope decision port.
        command: The upload intent, including the content stream.
        caller: The authenticated caller (the uploader).
        max_upload_bytes: Maximum accepted upload size in bytes.

    Returns:
        The stored document's metadata.

    Raises:
        AppealScopeDeniedError: The caller may not modify the named appeal, so they may not attach
            evidence to it.
        AppealScopeUnavailableError: No trusted scope decision could be obtained.
        UploadTooLargeError: If the content exceeds ``max_upload_bytes``.
        StorageFailureError: If the backend failed to store the content.
    """
    if command.ticket_id is not None:
        # Storing evidence against an appeal changes that appeal's record, so the *mutation*
        # decision applies — a read decision would let an audit role's breadth authorize a write.
        await scope.ensure_appeal_write_access(command.ticket_id, caller.access_token)

    repository = DocumentRepository(session)
    now = datetime.now(UTC)
    document = Document(
        id=uuid7(),
        ticket_id=command.ticket_id,
        message_id=command.message_id,
        original_filename=sanitize_filename(command.filename),
        storage_backend=storage.backend_name,
        storage_key=generate_storage_key(now),
        content_type=_normalize_content_type(command.content_type),
        size_bytes=0,
        document_type_code=command.document_type_code,
        version=1,
        status=DocumentStatus.UPLOADING,
        created_by=command.uploaded_by,
        created_at=now,
    )
    repository.add(document)
    # Durable before the first byte is written: an interrupted upload must leave a discoverable row
    # pointing at its storage key, never an untracked file on the volume.
    await session.commit()

    try:
        size_bytes = await storage.save(document.storage_key, command.chunks, max_upload_bytes)
    except StorageLimitExceededError as exc:
        await _mark_failed(session, document)
        raise UploadTooLargeError(str(exc)) from exc
    except Exception as exc:
        _logger.exception("storing document %s failed", document.id)
        await _mark_failed(session, document)
        raise StorageFailureError("failed to store the document content") from exc

    document.size_bytes = size_bytes
    document.status = DocumentStatus.AVAILABLE
    await session.commit()
    return document


async def _mark_failed(session: AsyncSession, document: Document) -> None:
    """Record a failed upload so the document is discoverable but never downloadable.

    Args:
        session: The active database session; this function commits it.
        document: The document whose upload failed.
    """
    document.status = DocumentStatus.UPLOAD_FAILED
    await session.commit()


async def get_document(
    session: AsyncSession, scope: AppealScopeChecker, document_id: uuid.UUID, caller: Caller
) -> Document:
    """Load a document's metadata for a caller allowed to see it.

    Args:
        session: The active database session.
        scope: The appeal-scope decision port.
        document_id: The document identifier.
        caller: The authenticated caller.

    Returns:
        The document metadata.

    Raises:
        DocumentNotFoundError: If the document does not exist or has been soft-deleted.
        AppealScopeDeniedError: If the caller is outside the appeal's scope.
        AppealScopeUnavailableError: If no trusted decision could be obtained.
    """
    document = await DocumentRepository(session).get(document_id)
    if document is None:
        raise DocumentNotFoundError(f"document {document_id} was not found")
    await _authorize_document(document, caller, scope)
    return document


async def open_document_content(
    session: AsyncSession,
    storage: FileStorage,
    scope: AppealScopeChecker,
    document_id: uuid.UUID,
    caller: Caller,
) -> tuple[Document, AsyncIterator[bytes]]:
    """Open a document's content for streaming, enforcing scope and the availability gate.

    Only an ``AVAILABLE`` document may be served. The same gate carries the docs/06 rule that
    content stays inaccessible until it is known clean once TASK_03A-2 adds scanning: a document
    awaiting or failing a scan simply never reaches ``AVAILABLE``.

    Args:
        session: The active database session.
        storage: The storage backend holding the bytes.
        scope: The appeal-scope decision port.
        document_id: The document identifier.
        caller: The authenticated caller.

    Returns:
        A tuple of the document metadata and an async iterator over its content.

    Raises:
        DocumentNotFoundError: If the document does not exist or has been soft-deleted.
        AppealScopeDeniedError: If the caller is outside the appeal's scope.
        AppealScopeUnavailableError: If no trusted decision could be obtained.
        DocumentNotAvailableError: If the document is not in a downloadable status.
        StorageFailureError: If the stored object is missing or unreadable.
    """
    document = await get_document(session, scope, document_id, caller)
    if document.status not in DOWNLOADABLE_STATUSES:
        raise DocumentNotAvailableError(document.status.value)
    try:
        stream = await storage.open_stream(document.storage_key)
    except StoredObjectMissingError as exc:
        # Metadata and storage have diverged; surfacing 404 here would misreport an existing record.
        _logger.error("stored object missing for document %s", document.id)
        raise StorageFailureError("the stored object is unavailable") from exc
    return document, stream


async def list_ticket_documents(
    session: AsyncSession, scope: AppealScopeChecker, query: DocumentListQuery, caller: Caller
) -> tuple[Sequence[Document], int]:
    """List one page of an appeal's documents, for a caller allowed to see that appeal.

    Args:
        session: The active database session.
        scope: The appeal-scope decision port.
        query: The listing query (appeal, page, page size).
        caller: The authenticated caller.

    Returns:
        A tuple of the page's documents and the total number of matching documents.

    Raises:
        AppealScopeDeniedError: If the caller may not reach the appeal.
        AppealScopeUnavailableError: If no trusted decision could be obtained.
    """
    await scope.ensure_appeal_read_access(query.ticket_id, caller.access_token)
    return await DocumentRepository(session).list_for_ticket(
        query.ticket_id, page=query.page, page_size=query.page_size
    )


async def link_document(
    session: AsyncSession, scope: AppealScopeChecker, command: LinkDocumentCommand, caller: Caller
) -> Document:
    """Link a document to an appeal.

    The caller must be allowed to **modify** both sides: the document as it stands (its current
    appeal, or being its uploader while it is unlinked) and the destination appeal. Both are
    mutation decisions, not read decisions (CR-DOC-HIGH-002). The transition itself is a single
    conditional update, so two concurrent links to different appeals cannot both succeed — one wins
    and the other is a conflict (CR-DOC-MEDIUM-002). Linkage is write-once evidence: a document
    already attached to another appeal is not silently moved (docs/06). Re-linking to the same
    appeal is idempotent and may refresh the mail-message reference.

    Args:
        session: The active database session; this function commits it.
        scope: The appeal-scope decision port.
        command: The linking intent.
        caller: The authenticated caller.

    Returns:
        The updated document metadata.

    Raises:
        DocumentNotFoundError: If the document does not exist or has been soft-deleted.
        AppealScopeDeniedError: If the caller may not modify the document or the destination
            appeal.
        AppealScopeUnavailableError: If no trusted decision could be obtained.
        DocumentAlreadyLinkedError: If the document belongs to a different appeal.
    """
    document = await DocumentRepository(session).get(command.document_id)
    if document is None:
        raise DocumentNotFoundError(f"document {command.document_id} was not found")
    await _authorize_document(document, caller, scope, for_write=True)
    await scope.ensure_appeal_write_access(command.ticket_id, caller.access_token)

    repository = DocumentRepository(session)
    linked = await repository.link_to_ticket(
        command.document_id, command.ticket_id, command.message_id
    )
    if not linked:
        await session.rollback()
        # The conditional update matched nothing: either the row disappeared (deleted) or it now
        # belongs to another appeal. Re-read to report the accurate outcome.
        current = await repository.get(command.document_id)
        if current is None:
            raise DocumentNotFoundError(f"document {command.document_id} was not found")
        raise DocumentAlreadyLinkedError(
            f"document {command.document_id} is already linked to another appeal"
        )
    await session.commit()
    document = await repository.get(command.document_id)
    if document is None:  # pragma: no cover - the row was just updated inside this transaction.
        raise DocumentNotFoundError(f"document {command.document_id} was not found")
    return document

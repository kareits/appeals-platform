"""Pydantic request/response schemas for the document API.

All models serialize with camelCase field names (docs/05). The upload request is multipart rather
than JSON, so its fields are declared as form parameters on the route; the schemas here cover the
JSON bodies and every JSON response.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel

from document_service.domain.enums import DocumentStatus
from document_service.infrastructure.models import Document

# Bounded coded value aligned with the database column limit, so oversized input is rejected with
# 422 by Pydantic instead of failing only in PostgreSQL. Mirrored in the committed contract.
CodeStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class RequestModel(BaseModel):
    """Strict base for HTTP request bodies.

    Input must use the camelCase aliases (``populate_by_name=False``) and unknown properties are
    rejected (``extra="forbid"``), so the runtime schema advertises ``additionalProperties: false``
    and matches the committed contract exactly.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid")


class ResponseModel(BaseModel):
    """Base for HTTP responses: camelCase output, snake_case construction by the mappers."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LinkDocumentRequest(RequestModel):
    """Request body for linking a document to an appeal.

    Attributes:
        ticket_id: The appeal to link the document to.
        message_id: The mail message the document arrived with, when applicable.
    """

    ticket_id: uuid.UUID
    message_id: uuid.UUID | None = None


class DocumentResponse(ResponseModel):
    """Document metadata returned by the API.

    Attributes:
        id: Internal document identifier (UUIDv7).
        ticket_id: Linked appeal, or ``None`` while unlinked.
        message_id: Mail message the document arrived with, when applicable.
        original_filename: Sanitized original filename (never a storage path).
        storage_backend: Backend holding the bytes (ADR-014).
        content_type: Content type declared at upload; recorded, not trusted.
        size_bytes: Stored size in bytes.
        document_type_code: Business document-type code, when supplied.
        version: Document version number.
        status: Storage lifecycle status; only ``AVAILABLE`` is downloadable.
        created_by: Verified subject that uploaded the document.
        created_at: Upload timestamp (UTC).
        deleted_at: Soft-deletion timestamp (EP-4).
    """

    id: uuid.UUID
    ticket_id: uuid.UUID | None
    message_id: uuid.UUID | None
    original_filename: str
    storage_backend: str
    content_type: str
    size_bytes: int
    document_type_code: str | None
    version: int
    status: DocumentStatus
    created_by: uuid.UUID
    created_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_document(cls, document: Document) -> Self:
        """Map a stored document to its API representation.

        The storage key is deliberately **not** exposed: it is an internal location, and publishing
        it would leak the storage layout that ADR-014 keeps replaceable (and docs/06 keeps random).

        Args:
            document: The document metadata row.

        Returns:
            The response model.
        """
        return cls(
            id=document.id,
            ticket_id=document.ticket_id,
            message_id=document.message_id,
            original_filename=document.original_filename,
            storage_backend=document.storage_backend,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            document_type_code=document.document_type_code,
            version=document.version,
            status=document.status,
            created_by=document.created_by,
            created_at=document.created_at,
            deleted_at=document.deleted_at,
        )


class PageMeta(ResponseModel):
    """Pagination metadata.

    Attributes:
        page: 1-based page number.
        page_size: Page size.
        total: Total number of matching documents.
    """

    page: int
    page_size: int
    total: int


class PaginatedDocuments(ResponseModel):
    """A page of document metadata.

    Attributes:
        items: The documents on this page.
        page: Pagination metadata.
    """

    # Both fields are required so the generated schema matches the committed contract exactly.
    items: list[DocumentResponse]
    page: PageMeta

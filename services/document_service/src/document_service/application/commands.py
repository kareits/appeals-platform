"""Command and query DTOs for the document use cases.

These carry already-authenticated intent from the API layer into the application layer. The actor
(``uploaded_by``) is always the verified token subject, never client input.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    """The authenticated caller a use case acts for.

    Attributes:
        subject: The verified token subject; the trusted actor recorded on stored data.
        access_token: The caller's own bearer token, forwarded when a scope decision has to be made
            on their behalf by another service (never a service identity — see
            :mod:`document_service.domain.scope`).
    """

    subject: uuid.UUID
    access_token: str


@dataclass
class UploadDocumentCommand:
    """Intent to store an uploaded file and record its metadata.

    Attributes:
        filename: The untrusted filename declared by the client; sanitized by the use case.
        content_type: The content type declared by the client; recorded but not trusted.
        chunks: The uploaded content as an async iterator of byte chunks, streamed straight to
            storage so a large document is never buffered in memory.
        ticket_id: The appeal to link the document to immediately, when supplied.
        message_id: The mail message the document arrived with, when applicable.
        document_type_code: Business document-type code, when supplied.
        uploaded_by: The verified caller subject recorded as the uploader.
    """

    filename: str | None
    content_type: str | None
    chunks: AsyncIterator[bytes]
    ticket_id: uuid.UUID | None
    message_id: uuid.UUID | None
    document_type_code: str | None
    uploaded_by: uuid.UUID


@dataclass(frozen=True)
class LinkDocumentCommand:
    """Intent to link a stored document to an appeal.

    Attributes:
        document_id: The document to link.
        ticket_id: The appeal to link it to.
        message_id: The mail message the document arrived with, when applicable.
    """

    document_id: uuid.UUID
    ticket_id: uuid.UUID
    message_id: uuid.UUID | None


@dataclass(frozen=True)
class DocumentListQuery:
    """A request for one page of an appeal's documents.

    Attributes:
        ticket_id: The appeal whose documents to list.
        page: 1-based page number.
        page_size: Maximum number of documents per page.
    """

    ticket_id: uuid.UUID
    page: int
    page_size: int

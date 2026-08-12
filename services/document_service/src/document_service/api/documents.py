"""HTTP routes for the document API.

Handlers are thin: they authenticate and authorize the caller, translate the request into a command
or query, invoke the application use case, and map results (and application errors) to responses. No
business logic lives here (root ``CLAUDE.md``).

Every route authenticates the bearer token independently — the document service serves file bytes
and is a security boundary in its own right, reachable directly without the BFF — and enforces a
permission claim. Object-level access (may this caller reach *this* appeal?) is decided inside the
use cases through the appeal-scope port and fails closed. The uploader recorded on a document is
always the verified caller subject, never client input.
"""
# Path and query parameters are named in camelCase to match the committed contract exactly; that is
# a wire concern, not a Python naming choice, so the argument-name rule is disabled for this module.
# ruff: noqa: N803

from __future__ import annotations

import urllib.parse
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from document_service.api.dependencies import (
    build_problem,
    declare_correlation_id,
    get_max_upload_bytes,
    get_scope_checker,
    get_session,
    get_storage,
    require_caller,
    require_permission,
)
from document_service.api.problems import problem_responses
from document_service.api.schemas import (
    CodeStr,
    DocumentResponse,
    LinkDocumentRequest,
    PageMeta,
    PaginatedDocuments,
)
from document_service.application import use_cases
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
from document_service.domain.permissions import DocumentPermission
from document_service.domain.scope import (
    AppealScopeChecker,
    AppealScopeDeniedError,
    AppealScopeUnavailableError,
)
from document_service.domain.storage import STREAM_CHUNK_SIZE, FileStorage
from document_service.infrastructure.auth_tokens import DocumentClaims

# The correlation-ID header is declared for every operation (see ``declare_correlation_id``).
router = APIRouter(
    prefix="/api/v1", tags=["documents"], dependencies=[Depends(declare_correlation_id)]
)

# ASCII fallback used in ``Content-Disposition`` when the sanitized filename is not representable in
# latin-1; the RFC 5987 ``filename*`` parameter always carries the real (UTF-8) name.
_ASCII_FALLBACK_FILENAME = "document"

# Response headers declared on the JSON success responses. ``CorrelationIdMiddleware`` sets the
# header on every response and the committed contract declares it, so the runtime document does
# too.
_CORRELATION_HEADER = {
    "X-Correlation-ID": {
        "schema": {"type": "string"},
        "description": "Correlation identifier for this request.",
    }
}


async def _iter_upload(upload: UploadFile) -> AsyncIterator[bytes]:
    """Yield an uploaded file's content in bounded chunks.

    Args:
        upload: The multipart upload.

    Yields:
        Successive chunks of the uploaded content.
    """
    while True:
        chunk = await upload.read(STREAM_CHUNK_SIZE)
        if not chunk:
            return
        yield chunk


def _content_disposition(filename: str) -> str:
    """Build an attachment ``Content-Disposition`` header value for a sanitized filename.

    The filename is already sanitized (no quotes, control characters, or path separators), so it
    cannot break out of the header. Both forms are emitted: a latin-1-safe ``filename`` for old
    clients and the RFC 5987 ``filename*`` carrying the exact UTF-8 name.

    Args:
        filename: The sanitized original filename.

    Returns:
        The header value.
    """
    try:
        filename.encode("latin-1")
        ascii_name = filename
    except UnicodeEncodeError:
        ascii_name = _ASCII_FALLBACK_FILENAME
    quoted = urllib.parse.quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


def _scope_problem(error: Exception) -> Exception:
    """Map an appeal-scope failure to its HTTP problem.

    A denial is 403 with no detail about the appeal, so a caller outside its scope cannot use the
    response to learn whether it exists. An unavailable decision is 503, kept distinct from a
    denial: the request is refused because authorization could not be decided, and refusing is what
    keeps an outage of the decision point from becoming open access.

    Args:
        error: The raised scope error.

    Returns:
        The problem-detail error to raise.
    """
    if isinstance(error, AppealScopeDeniedError):
        return build_problem(403, "Forbidden", "access to the referenced appeal is not permitted")
    return build_problem(
        503, "Authorization unavailable", "the appeal-scope decision is currently unavailable"
    )


@router.post(
    "/documents",
    operation_id="uploadDocument",
    summary="Upload a document.",
    status_code=201,
    response_model=DocumentResponse,
    responses={
        201: {"description": "The document was stored.", "headers": _CORRELATION_HEADER},
        **problem_responses(400, 401, 403, 413, 422, 500, 503),
    },
)
async def upload_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[FileStorage, Depends(get_storage)],
    scope: Annotated[AppealScopeChecker, Depends(get_scope_checker)],
    max_upload_bytes: Annotated[int, Depends(get_max_upload_bytes)],
    _claims: Annotated[DocumentClaims, Depends(require_permission(DocumentPermission.WRITE))],
    caller: Annotated[Caller, Depends(require_caller)],
    file: Annotated[UploadFile, File(description="The file content.")],
    ticketId: Annotated[uuid.UUID | None, Form(description="Appeal to link the document to.")] = (
        None
    ),
    messageId: Annotated[uuid.UUID | None, Form(description="Originating mail message.")] = None,
    documentTypeCode: Annotated[
        CodeStr | None, Form(description="Business document-type code.")
    ] = None,
) -> DocumentResponse:
    """Store an uploaded file and return its metadata.

    Args:
        session: The request-scoped database session.
        storage: The storage backend.
        scope: The appeal-scope decision port.
        max_upload_bytes: The configured upload size limit, applied to the **file** bytes.
        _claims: The verified caller claims (permission gate only).
        caller: The authenticated caller, that is, the uploader.
        file: The multipart file part.
        ticketId: Optional appeal to link the document to immediately.
        messageId: Optional originating mail message.
        documentTypeCode: Optional business document-type code.

    Returns:
        The stored document's metadata.

    Raises:
        ProblemDetailError: 403/503 when the appeal-scope decision denies or is unavailable, 413
            when the file exceeds the size limit, or 500 when the storage backend fails.
    """
    command = UploadDocumentCommand(
        filename=file.filename,
        content_type=file.content_type,
        chunks=_iter_upload(file),
        ticket_id=ticketId,
        message_id=messageId,
        document_type_code=documentTypeCode,
        uploaded_by=caller.subject,
    )
    try:
        document = await use_cases.upload_document(
            session, storage, scope, command, caller, max_upload_bytes=max_upload_bytes
        )
    except (AppealScopeDeniedError, AppealScopeUnavailableError) as exc:
        raise _scope_problem(exc) from exc
    except UploadTooLargeError as exc:
        raise build_problem(
            413,
            "Payload too large",
            f"the file exceeds the maximum of {max_upload_bytes} bytes",
        ) from exc
    except StorageFailureError as exc:
        raise build_problem(500, "Storage failure", "the document could not be stored") from exc
    return DocumentResponse.from_document(document)


@router.get(
    "/documents",
    operation_id="listTicketDocuments",
    summary="List the documents of an appeal.",
    response_model=PaginatedDocuments,
    responses={
        200: {
            "description": "A page of documents linked to the appeal.",
            "headers": _CORRELATION_HEADER,
        },
        **problem_responses(401, 403, 422, 503),
    },
)
async def list_ticket_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: Annotated[AppealScopeChecker, Depends(get_scope_checker)],
    _claims: Annotated[DocumentClaims, Depends(require_permission(DocumentPermission.READ))],
    caller: Annotated[Caller, Depends(require_caller)],
    ticketId: Annotated[uuid.UUID, Query(description="Appeal identifier.")],
    page: Annotated[int, Query(ge=1, description="1-based page number.")] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100, description="Page size.")] = 20,
) -> PaginatedDocuments:
    """List one page of an appeal's documents, newest first.

    Args:
        session: The request-scoped database session.
        scope: The appeal-scope decision port.
        _claims: The verified caller claims (permission gate only).
        caller: The authenticated caller.
        ticketId: The appeal whose documents to list.
        page: 1-based page number.
        pageSize: Page size.

    Returns:
        The page of document metadata.

    Raises:
        ProblemDetailError: 403 when the caller may not reach the appeal, or 503 when the decision
            is unavailable.
    """
    try:
        documents, total = await use_cases.list_ticket_documents(
            session,
            scope,
            DocumentListQuery(ticket_id=ticketId, page=page, page_size=pageSize),
            caller,
        )
    except (AppealScopeDeniedError, AppealScopeUnavailableError) as exc:
        raise _scope_problem(exc) from exc
    return PaginatedDocuments(
        items=[DocumentResponse.from_document(document) for document in documents],
        page=PageMeta(page=page, page_size=pageSize, total=total),
    )


@router.get(
    "/documents/{documentId}",
    operation_id="getDocument",
    summary="Get document metadata by identifier.",
    response_model=DocumentResponse,
    responses={
        200: {"description": "The document metadata.", "headers": _CORRELATION_HEADER},
        **problem_responses(401, 403, 404, 422, 503),
    },
)
async def get_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: Annotated[AppealScopeChecker, Depends(get_scope_checker)],
    _claims: Annotated[DocumentClaims, Depends(require_permission(DocumentPermission.READ))],
    caller: Annotated[Caller, Depends(require_caller)],
    documentId: uuid.UUID,
) -> DocumentResponse:
    """Return a document's metadata.

    Args:
        session: The request-scoped database session.
        scope: The appeal-scope decision port.
        _claims: The verified caller claims (permission gate only).
        caller: The authenticated caller.
        documentId: The document identifier.

    Returns:
        The document metadata.

    Raises:
        ProblemDetailError: 404 when the document does not exist or has been soft-deleted, 403 when
            the caller is outside its appeal's scope, or 503 when the decision is unavailable.
    """
    try:
        document = await use_cases.get_document(session, scope, documentId, caller)
    except DocumentNotFoundError as exc:
        raise build_problem(404, "Document not found", str(exc)) from exc
    except (AppealScopeDeniedError, AppealScopeUnavailableError) as exc:
        raise _scope_problem(exc) from exc
    return DocumentResponse.from_document(document)


@router.get(
    "/documents/{documentId}/content",
    operation_id="downloadDocument",
    summary="Download the document content.",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The document content stream.",
            "content": {
                "application/octet-stream": {
                    # OpenAPI 3.1 expresses binary payloads with ``contentMediaType`` (JSON Schema
                    # 2020-12), not the 3.0 ``format: binary``.
                    "schema": {"type": "string", "contentMediaType": "application/octet-stream"}
                }
            },
            "headers": {
                **_CORRELATION_HEADER,
                "Content-Disposition": {
                    "schema": {"type": "string"},
                    "description": (
                        "Always an attachment disposition carrying the sanitized original filename."
                    ),
                },
                "X-Content-Type-Options": {
                    "schema": {"type": "string"},
                    "description": 'Always "nosniff".',
                },
            },
        },
        **problem_responses(401, 403, 404, 409, 422, 500, 503),
    },
)
async def download_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[FileStorage, Depends(get_storage)],
    scope: Annotated[AppealScopeChecker, Depends(get_scope_checker)],
    _claims: Annotated[DocumentClaims, Depends(require_permission(DocumentPermission.READ))],
    caller: Annotated[Caller, Depends(require_caller)],
    documentId: uuid.UUID,
) -> StreamingResponse:
    """Stream a document's content as an attachment.

    The response is always an untyped attachment with ``X-Content-Type-Options: nosniff``: the
    stored content type is client-declared and unverified, so serving it back would let an uploaded
    HTML or script file be rendered in the platform's origin. Safe preview is EP-4.

    Args:
        session: The request-scoped database session.
        storage: The storage backend.
        scope: The appeal-scope decision port.
        _claims: The verified caller claims (permission gate only).
        caller: The authenticated caller.
        documentId: The document identifier.

    Returns:
        A streaming response carrying the document content.

    Raises:
        ProblemDetailError: 404 when the document does not exist, 403/503 on the appeal-scope
            decision, 409 when its status forbids download, or 500 when the stored object is
            unavailable.
    """
    try:
        document, stream = await use_cases.open_document_content(
            session, storage, scope, documentId, caller
        )
    except DocumentNotFoundError as exc:
        raise build_problem(404, "Document not found", str(exc)) from exc
    except (AppealScopeDeniedError, AppealScopeUnavailableError) as exc:
        raise _scope_problem(exc) from exc
    except DocumentNotAvailableError as exc:
        raise build_problem(409, "Document not available", str(exc)) from exc
    except StorageFailureError as exc:
        raise build_problem(500, "Storage failure", "the document content is unavailable") from exc
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": _content_disposition(document.original_filename),
            "Content-Length": str(document.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/documents/{documentId}/link",
    operation_id="linkDocument",
    summary="Link a document to an appeal.",
    response_model=DocumentResponse,
    responses={
        200: {
            "description": "The document is linked to the appeal.",
            "headers": _CORRELATION_HEADER,
        },
        **problem_responses(401, 403, 404, 409, 422, 503),
    },
)
async def link_document(
    session: Annotated[AsyncSession, Depends(get_session)],
    scope: Annotated[AppealScopeChecker, Depends(get_scope_checker)],
    _claims: Annotated[DocumentClaims, Depends(require_permission(DocumentPermission.WRITE))],
    caller: Annotated[Caller, Depends(require_caller)],
    documentId: uuid.UUID,
    payload: LinkDocumentRequest,
) -> DocumentResponse:
    """Link a document to an appeal.

    Args:
        session: The request-scoped database session.
        scope: The appeal-scope decision port.
        _claims: The verified caller claims (permission gate only).
        caller: The authenticated caller.
        documentId: The document to link.
        payload: The linking request.

    Returns:
        The updated document metadata.

    Raises:
        ProblemDetailError: 404 when the document does not exist, 403/503 on the appeal-scope
            decision, or 409 when it already belongs to a different appeal.
    """
    command = LinkDocumentCommand(
        document_id=documentId, ticket_id=payload.ticket_id, message_id=payload.message_id
    )
    try:
        document = await use_cases.link_document(session, scope, command, caller)
    except DocumentNotFoundError as exc:
        raise build_problem(404, "Document not found", str(exc)) from exc
    except (AppealScopeDeniedError, AppealScopeUnavailableError) as exc:
        raise _scope_problem(exc) from exc
    except DocumentAlreadyLinkedError as exc:
        raise build_problem(409, "Document already linked", str(exc)) from exc
    return DocumentResponse.from_document(document)

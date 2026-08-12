"""Integration tests for the document API over an ASGI client.

The acceptance path for TASK_03A-1 (upload -> list -> download) is covered end to end, together with
the lifecycle gate, linkage rules, and the response hardening that keeps untrusted content from
being rendered by a browser.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

_PDF_BYTES = b"%PDF-1.4 fake content for tests"

# The file-byte ceiling configured for the ``small_limit_client`` fixture.
_SMALL_LIMIT = 1024


async def _upload(
    client: AsyncClient,
    *,
    filename: str = "statement.pdf",
    content: bytes = _PDF_BYTES,
    content_type: str = "application/pdf",
    **fields: str,
) -> dict[str, Any]:
    """Upload a document and return the parsed response body.

    Args:
        client: The HTTP client.
        filename: The filename declared in the multipart part.
        content: The uploaded bytes.
        content_type: The content type declared in the multipart part.
        **fields: Additional form fields (``ticketId``, ``messageId``, ``documentTypeCode``).

    Returns:
        The parsed document metadata.
    """
    response = await client.post(
        "/api/v1/documents",
        files={"file": (filename, content, content_type)},
        data=fields,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_upload_list_download_round_trip(client: AsyncClient) -> None:
    """The acceptance path works: an uploaded document is listed and downloaded intact."""
    ticket_id = str(uuid.uuid4())

    uploaded = await _upload(client, ticketId=ticket_id)

    assert uploaded["status"] == "AVAILABLE"
    assert uploaded["ticketId"] == ticket_id
    assert uploaded["sizeBytes"] == len(_PDF_BYTES)
    assert uploaded["storageBackend"] == "local"

    listed = await client.get("/api/v1/documents", params={"ticketId": ticket_id})
    assert listed.status_code == 200
    page = listed.json()
    assert page["page"] == {"page": 1, "pageSize": 20, "total": 1}
    assert [item["id"] for item in page["items"]] == [uploaded["id"]]

    downloaded = await client.get(f"/api/v1/documents/{uploaded['id']}/content")
    assert downloaded.status_code == 200
    assert downloaded.content == _PDF_BYTES


async def test_metadata_never_exposes_the_storage_key(client: AsyncClient) -> None:
    """The internal storage location stays server-side (docs/06, ADR-014)."""
    uploaded = await _upload(client)

    fetched = await client.get(f"/api/v1/documents/{uploaded['id']}")

    assert fetched.status_code == 200
    assert "storageKey" not in fetched.json()
    assert "storage_key" not in fetched.text


async def test_download_is_served_as_an_untrusted_attachment(client: AsyncClient) -> None:
    """Content is never returned with a renderable media type, whatever the client declared."""
    uploaded = await _upload(
        client,
        filename="payload.html",
        content=b"<script>alert(1)</script>",
        content_type="text/html",
    )

    downloaded = await client.get(f"/api/v1/documents/{uploaded['id']}/content")

    assert downloaded.headers["content-type"] == "application/octet-stream"
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    # The declared type is recorded as metadata only.
    assert uploaded["contentType"] == "text/html"


async def test_uploaded_filename_is_sanitized(client: AsyncClient) -> None:
    """A traversal filename is stored (and echoed) as a plain basename."""
    uploaded = await _upload(client, filename="../../etc/passwd")

    assert uploaded["originalFilename"] == "passwd"
    downloaded = await client.get(f"/api/v1/documents/{uploaded['id']}/content")
    assert "passwd" in downloaded.headers["content-disposition"]
    assert ".." not in downloaded.headers["content-disposition"]


@pytest.mark.parametrize("file_size", [_SMALL_LIMIT - 1, _SMALL_LIMIT])
async def test_files_up_to_the_limit_are_accepted(
    small_limit_client: AsyncClient, file_size: int
) -> None:
    """The configured ceiling applies to file bytes, not to the multipart request size.

    Regression guard for CR-DOC-MEDIUM-001: comparing the whole request length against the limit
    rejected valid in-limit files, because boundaries and part headers consumed part of the
    advertised allowance. Both sizes here produce a multipart request larger than the limit.
    """
    ticket_id = str(uuid.uuid4())

    response = await small_limit_client.post(
        "/api/v1/documents",
        files={"file": ("evidence.bin", b"x" * file_size, "application/octet-stream")},
        data={"ticketId": ticket_id},
    )

    assert response.status_code == 201, response.text
    assert response.json()["sizeBytes"] == file_size
    downloaded = await small_limit_client.get(f"/api/v1/documents/{response.json()['id']}/content")
    assert len(downloaded.content) == file_size


async def test_file_over_the_limit_is_rejected_and_recorded_as_failed(
    small_limit_client: AsyncClient,
) -> None:
    """One byte over the limit yields 413 and never becomes downloadable.

    The metadata row survives on purpose: it names the storage key, so an interrupted or rejected
    upload stays discoverable for reconciliation instead of leaving an untracked file on the volume.
    """
    ticket_id = str(uuid.uuid4())

    response = await small_limit_client.post(
        "/api/v1/documents",
        files={"file": ("big.bin", b"x" * (_SMALL_LIMIT + 1), "application/octet-stream")},
        data={"ticketId": ticket_id},
    )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    listed = await small_limit_client.get("/api/v1/documents", params={"ticketId": ticket_id})
    items = listed.json()["items"]
    assert [item["status"] for item in items] == ["UPLOAD_FAILED"]
    download = await small_limit_client.get(f"/api/v1/documents/{items[0]['id']}/content")
    assert download.status_code == 409


async def test_streamed_upload_over_the_limit_is_rejected(
    small_limit_client: AsyncClient,
) -> None:
    """A chunked upload with no Content-Length is stopped by the streaming guard."""
    ticket_id = str(uuid.uuid4())

    async def _oversized_body() -> AsyncIterator[bytes]:
        """Stream a multipart body larger than the limit without declaring its length.

        Yields:
            The multipart body in chunks.
        """
        yield (
            b'--boundary\r\nContent-Disposition: form-data; name="ticketId"\r\n\r\n'
            + ticket_id.encode()
            + b"\r\n"
        )
        yield (
            b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="big.bin"\r\n'
            b"Content-Type: application/octet-stream\r\n\r\n"
        )
        yield b"x" * (_SMALL_LIMIT * 4)
        yield b"\r\n--boundary--\r\n"

    response = await small_limit_client.post(
        "/api/v1/documents",
        content=_oversized_body(),
        headers={"Content-Type": "multipart/form-data; boundary=boundary"},
    )

    assert response.status_code == 413


async def test_unlinked_upload_can_be_linked_later(client: AsyncClient) -> None:
    """A document may be stored first and attached to an appeal afterwards."""
    ticket_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    uploaded = await _upload(client)
    assert uploaded["ticketId"] is None

    linked = await client.post(
        f"/api/v1/documents/{uploaded['id']}/link",
        json={"ticketId": ticket_id, "messageId": message_id},
    )

    assert linked.status_code == 200
    assert linked.json()["ticketId"] == ticket_id
    assert linked.json()["messageId"] == message_id
    listed = await client.get("/api/v1/documents", params={"ticketId": ticket_id})
    assert listed.json()["page"]["total"] == 1


async def test_relinking_to_the_same_appeal_is_idempotent(client: AsyncClient) -> None:
    """Repeating a link is not an error and does not duplicate anything."""
    ticket_id = str(uuid.uuid4())
    uploaded = await _upload(client, ticketId=ticket_id)

    first = await client.post(
        f"/api/v1/documents/{uploaded['id']}/link", json={"ticketId": ticket_id}
    )
    second = await client.post(
        f"/api/v1/documents/{uploaded['id']}/link", json={"ticketId": ticket_id}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["ticketId"] == ticket_id


async def test_relinking_to_a_different_appeal_is_refused(client: AsyncClient) -> None:
    """Evidence is not silently moved between appeals (docs/06)."""
    uploaded = await _upload(client, ticketId=str(uuid.uuid4()))

    response = await client.post(
        f"/api/v1/documents/{uploaded['id']}/link", json={"ticketId": str(uuid.uuid4())}
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_link_body_rejects_unknown_properties(client: AsyncClient) -> None:
    """Request bodies are strict, matching the contract's additionalProperties: false."""
    uploaded = await _upload(client)

    response = await client.post(
        f"/api/v1/documents/{uploaded['id']}/link",
        json={"ticketId": str(uuid.uuid4()), "unexpected": "value"},
    )

    assert response.status_code == 422


async def test_unknown_document_is_not_found(client: AsyncClient) -> None:
    """A missing identifier yields 404 for both metadata and content."""
    missing = uuid.uuid4()

    assert (await client.get(f"/api/v1/documents/{missing}")).status_code == 404
    assert (await client.get(f"/api/v1/documents/{missing}/content")).status_code == 404
    assert (
        await client.post(f"/api/v1/documents/{missing}/link", json={"ticketId": str(uuid.uuid4())})
    ).status_code == 404


async def test_listing_is_paginated_and_newest_first(client: AsyncClient) -> None:
    """Listing returns the requested page in creation order, newest first."""
    ticket_id = str(uuid.uuid4())
    first = await _upload(client, filename="first.pdf", ticketId=ticket_id)
    second = await _upload(client, filename="second.pdf", ticketId=ticket_id)

    page_one = await client.get(
        "/api/v1/documents", params={"ticketId": ticket_id, "page": 1, "pageSize": 1}
    )
    page_two = await client.get(
        "/api/v1/documents", params={"ticketId": ticket_id, "page": 2, "pageSize": 1}
    )

    assert page_one.json()["page"]["total"] == 2
    assert [item["id"] for item in page_one.json()["items"]] == [second["id"]]
    assert [item["id"] for item in page_two.json()["items"]] == [first["id"]]


async def test_listing_requires_a_ticket_identifier(client: AsyncClient) -> None:
    """Listing is always scoped to one appeal; an unscoped call is rejected."""
    response = await client.get("/api/v1/documents")
    assert response.status_code == 422


async def test_health_endpoints_report_database_and_storage(client: AsyncClient) -> None:
    """Readiness covers both the database and the storage volume."""
    live = await client.get("/health/live")
    ready = await client.get("/health/ready")

    assert live.json() == {"status": "alive"}
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "healthy", "storage": "healthy"}

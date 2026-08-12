"""Tests that stored files and their metadata survive a service restart.

TASK_03A-1 acceptance: "restart does not lose files". The restart is simulated at the ASGI level by
disposing of one application and building a second one over the same database and storage root — the
same thing a container restart does with a persistent volume.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from document_service.config import Settings
from document_service.main import create_app
from document_test_support import (
    FakeScopeChecker,
    auth_headers,
    build_settings,
    create_schema,
)
from mfo_testing import create_asgi_client


async def test_documents_survive_an_application_restart(tmp_path: Path) -> None:
    """A document uploaded by one application instance is served by the next one."""
    settings = build_settings(tmp_path)
    await create_schema(settings.database_url)
    ticket_id = str(uuid.uuid4())
    content = b"regulatory evidence bytes"
    header = auth_headers()

    async with create_asgi_client(create_app(settings, scope_checker=FakeScopeChecker())) as first:
        created = await first.post(
            "/api/v1/documents",
            files={"file": ("evidence.pdf", content, "application/pdf")},
            data={"ticketId": ticket_id},
            headers=header,
        )
        assert created.status_code == 201
        document_id = created.json()["id"]

    # A fresh application over the same database and storage root: the restart case.
    async with create_asgi_client(create_app(settings, scope_checker=FakeScopeChecker())) as second:
        listed = await second.get(
            "/api/v1/documents", params={"ticketId": ticket_id}, headers=header
        )
        downloaded = await second.get(f"/api/v1/documents/{document_id}/content", headers=header)

    assert [item["id"] for item in listed.json()["items"]] == [document_id]
    assert downloaded.status_code == 200
    assert downloaded.content == content


async def test_stored_bytes_live_under_the_configured_root(tmp_path: Path) -> None:
    """Uploaded content is written inside the storage root, under a random keyed path."""
    settings = build_settings(tmp_path)
    await create_schema(settings.database_url)
    header = auth_headers()

    async with create_asgi_client(create_app(settings, scope_checker=FakeScopeChecker())) as client:
        created = await client.post(
            "/api/v1/documents",
            files={"file": ("evidence.pdf", b"bytes", "application/pdf")},
            headers=header,
        )
        assert created.status_code == 201

    stored = [path for path in Path(settings.storage_root).rglob("*") if path.is_file()]
    assert len(stored) == 1
    # The object is addressed by a random key, never by the client's filename.
    assert stored[0].name != "evidence.pdf"
    assert stored[0].read_bytes() == b"bytes"


async def test_missing_stored_object_yields_a_server_error(tmp_path: Path) -> None:
    """Metadata without its bytes is a server-side inconsistency, not a 404."""
    settings = build_settings(tmp_path)
    await create_schema(settings.database_url)
    header = auth_headers()

    async with create_asgi_client(create_app(settings, scope_checker=FakeScopeChecker())) as client:
        created = await client.post(
            "/api/v1/documents",
            files={"file": ("evidence.pdf", b"bytes", "application/pdf")},
            headers=header,
        )
        document_id = created.json()["id"]

        # Simulate storage loss out of band (for example, a wiped volume).
        for path in Path(settings.storage_root).rglob("*"):
            if path.is_file():
                path.unlink()

        response = await client.get(f"/api/v1/documents/{document_id}/content", headers=header)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")


def test_unsupported_storage_backend_fails_fast(tmp_path: Path) -> None:
    """Configuring an unimplemented backend refuses to start instead of writing locally."""
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'documents.db'}",
        storage_root=tmp_path / "storage",
        storage_backend="gridfs",
    )

    try:
        create_app(settings, scope_checker=FakeScopeChecker())
    except ValueError as exc:
        assert "gridfs" in str(exc)
    else:  # pragma: no cover - the factory must not accept an unimplemented backend.
        raise AssertionError("an unsupported storage backend must not start")

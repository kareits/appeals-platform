"""Tests for document-service configuration resolution."""

from __future__ import annotations

from pathlib import Path

from document_service.config import DEFAULT_MAX_UPLOAD_BYTES, Settings
from sqlalchemy.engine import make_url


def test_database_url_is_built_from_discrete_parts() -> None:
    """Discrete host/user/name parts produce an asyncpg URL."""
    settings = Settings(
        db_host="postgres", db_user="document", db_password="secret", db_name="document_service"
    )

    url = make_url(settings.resolved_database_url())

    assert url.drivername == "postgresql+asyncpg"
    assert (url.host, url.username, url.password, url.database) == (
        "postgres",
        "document",
        "secret",
        "document_service",
    )


def test_uri_reserved_characters_in_the_password_survive_round_trip() -> None:
    """A password containing ``@:/?#`` is percent-encoded and parses back unchanged.

    Regression guard for the class of defect fixed as CR-BFF-R3-MEDIUM-003 in the other services:
    embedding a raw secret in a URL silently corrupts the host or database when it contains
    URI-reserved characters.
    """
    password = "rot@ted:p/a?ss#9f3a"
    settings = Settings(
        db_host="postgres", db_user="document", db_password=password, db_name="document_service"
    )

    url = make_url(settings.resolved_database_url())

    assert url.password == password
    assert url.host == "postgres"
    assert url.database == "document_service"


def test_plain_database_url_is_used_without_discrete_parts(tmp_path: Path) -> None:
    """Without discrete parts the configured URL is used verbatim (local SQLite/dev)."""
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'documents.db'}")

    assert settings.resolved_database_url() == settings.database_url


def test_defaults_are_local_friendly() -> None:
    """Defaults run the service without external infrastructure and cap uploads."""
    settings = Settings()

    assert settings.storage_backend == "local"
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES
    assert settings.jwt_algorithms == ("HS256",)

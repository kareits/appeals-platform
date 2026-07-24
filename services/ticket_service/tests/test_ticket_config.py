"""Tests for building the database URL safely from discrete parts (CR-BFF-R3-MEDIUM-003)."""

from __future__ import annotations

from sqlalchemy.engine import make_url
from ticket_service.config import Settings


def test_special_character_password_is_percent_encoded() -> None:
    """A password with URI-reserved characters is percent-encoded and round-trips correctly."""
    settings = Settings(
        db_host="postgres",
        db_user="ticket",
        db_name="ticket_service",
        db_password="p@ss:w/o?rd#x",
    )
    url = settings.resolved_database_url()
    # The raw reserved characters never appear unencoded in the authority section.
    assert "p@ss:w/o?rd#x" not in url
    parsed = make_url(url)
    # SQLAlchemy decodes the components back to the exact original values.
    assert parsed.password == "p@ss:w/o?rd#x"
    assert parsed.username == "ticket"
    assert parsed.host == "postgres"
    assert parsed.port == 5432
    assert parsed.database == "ticket_service"


def test_without_discrete_parts_falls_back_to_database_url() -> None:
    """Without host/user/name, the plain ``database_url`` is used (local SQLite/dev)."""
    settings = Settings(database_url="sqlite+aiosqlite:///./ticket_service.db")
    assert settings.resolved_database_url() == "sqlite+aiosqlite:///./ticket_service.db"

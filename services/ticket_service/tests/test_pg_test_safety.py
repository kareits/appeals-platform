"""Tests for the fail-closed destructive-PostgreSQL target guard.

These run without a database: they verify the guard rejects unsafe targets, requires an explicit
opt-in, and fails closed (raises) rather than skipping when the opt-in is set but the target is
unsafe (CR-BFF-R6-MEDIUM-002).
"""

from __future__ import annotations

import pytest
from pg_test_safety import (
    OPT_IN_ENV,
    URL_ENV,
    destructive_tests_enabled,
    is_safe_test_target,
    require_safe_test_url,
    unique_schema_name,
)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "sqlite+aiosqlite:///./ticket_test.db",  # not PostgreSQL
        "postgresql+asyncpg://u:p@localhost:5432/ticket_service",  # application database
        "postgresql+asyncpg://u:p@localhost:5432/postgres",  # system database
        "postgresql+asyncpg://u:p@localhost:5432/appeals",  # missing the _test sentinel
    ],
)
def test_rejects_unsafe_targets(url: str | None) -> None:
    """A non-PostgreSQL URL, an application/system database, or a missing sentinel is rejected."""
    assert is_safe_test_target(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@localhost:5432/ticket_service_test",
        "postgresql+asyncpg://postgres:postgres@db:5432/appeals_review_test",
    ],
)
def test_accepts_disposable_test_targets(url: str) -> None:
    """A PostgreSQL database whose name ends with the test sentinel is accepted."""
    assert is_safe_test_target(url) is True


def test_disabled_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Destructive tests stay disabled unless the opt-in flag and a URL are both present."""
    monkeypatch.setenv(URL_ENV, "postgresql+asyncpg://u:p@localhost:5432/ticket_service_test")
    monkeypatch.delenv(OPT_IN_ENV, raising=False)
    assert destructive_tests_enabled() is False
    monkeypatch.setenv(OPT_IN_ENV, "1")
    assert destructive_tests_enabled() is True


def test_require_safe_url_fails_closed_on_unsafe_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the opt-in set but an unsafe target, the guard raises instead of skipping."""
    monkeypatch.setenv(OPT_IN_ENV, "1")
    monkeypatch.setenv(URL_ENV, "postgresql+asyncpg://u:p@localhost:5432/ticket_service")
    with pytest.raises(RuntimeError, match="disposable PostgreSQL database"):
        require_safe_test_url()


def test_require_safe_url_returns_safe_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """A safe disposable target is returned unchanged."""
    url = "postgresql+asyncpg://u:p@localhost:5432/ticket_service_test"
    monkeypatch.setenv(URL_ENV, url)
    assert require_safe_test_url() == url


def test_unique_schema_names_are_disposable_and_distinct() -> None:
    """Generated schema names are namespaced and unique per call."""
    first = unique_schema_name()
    second = unique_schema_name()
    assert first.startswith("ticket_test_")
    assert first != second

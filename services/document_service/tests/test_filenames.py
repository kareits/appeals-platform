"""Unit tests for untrusted-filename sanitization (docs/06)."""

from __future__ import annotations

import pytest
from document_service.domain.filenames import (
    FALLBACK_FILENAME,
    MAX_FILENAME_LENGTH,
    sanitize_filename,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\config", "config"),
        ("/absolute/path/statement.xlsx", "statement.xlsx"),
        ("C:\\Users\\admin\\secret.docx", "secret.docx"),
        ("Заявление клиента.pdf", "Заявление клиента.pdf"),
        ('inject";rm -rf.txt', "injectrm -rf.txt"),
        ("with\nnewline.txt", "withnewline.txt"),
        ("trailing.dots...", "trailing.dots"),
    ],
)
def test_sanitize_filename_strips_dangerous_input(raw: str, expected: str) -> None:
    """Path components, separators, quotes, and control characters never survive."""
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "..", "../", "/", "\\", "..."])
def test_empty_or_path_only_names_fall_back(raw: str | None) -> None:
    """A name that sanitizes to nothing yields the deterministic fallback."""
    assert sanitize_filename(raw) == FALLBACK_FILENAME


def test_long_names_are_truncated() -> None:
    """An over-long filename is truncated to the storable maximum."""
    sanitized = sanitize_filename("a" * (MAX_FILENAME_LENGTH + 50) + ".pdf")
    assert len(sanitized) == MAX_FILENAME_LENGTH


def test_sanitized_name_never_contains_separators_or_quotes() -> None:
    """The result is safe to embed in a Content-Disposition header."""
    sanitized = sanitize_filename('a/b\\c:"d";e.txt')
    assert not set(sanitized) & set('/\\:;"')

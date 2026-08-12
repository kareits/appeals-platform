"""Filename sanitization rules.

A client-supplied filename is untrusted input that reaches three dangerous places: the filesystem,
the ``Content-Disposition`` response header, and any later export. It never reaches the filesystem
here (objects are addressed by a random storage key, see :mod:`document_service.domain.storage`),
but it is still stored and echoed back, so it is normalized once, at the boundary: path components,
control characters, and header-breaking characters are removed (docs/06 "filename sanitization").
"""

from __future__ import annotations

import unicodedata

# Upper bound on a stored filename. Long enough for real business documents, short enough to keep
# response headers and log lines bounded.
MAX_FILENAME_LENGTH = 255

# Substituted when the sanitized result would be empty (for example, a filename of "../..").
FALLBACK_FILENAME = "document"

# Characters that must never survive into a stored filename: path separators (both platforms),
# Windows drive/stream separators, quotes and semicolons (which would break or inject into a
# ``Content-Disposition`` header), and the wildcard/redirect characters that confuse shells.
_FORBIDDEN_CHARACTERS = set("/\\:;\"'<>|*?")


def sanitize_filename(raw: str | None) -> str:
    r"""Normalize an untrusted filename into a safe, storable display name.

    Unicode is normalized to NFC, path components are dropped (the basename after both ``/`` and
    ``\``), control characters and header-breaking characters are removed, surrounding whitespace
    and dots are stripped (a leading dot would hide the file and a trailing dot is invalid on
    Windows), and the result is truncated to :data:`MAX_FILENAME_LENGTH`. An empty or fully stripped
    name falls back to :data:`FALLBACK_FILENAME` so downstream formatting always has a value.

    Args:
        raw: The filename supplied by the client, or ``None``.

    Returns:
        A sanitized filename that contains no path components and no control characters.
    """
    if not raw:
        return FALLBACK_FILENAME
    normalized = unicodedata.normalize("NFC", raw)
    # Take the basename with respect to both separators: a POSIX server must still defend against a
    # Windows-style path ("..\\..\\secret.txt") because the string comes from an arbitrary client.
    basename = normalized.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(
        character
        for character in basename
        if character not in _FORBIDDEN_CHARACTERS and unicodedata.category(character) != "Cc"
    )
    cleaned = cleaned.strip().strip(".").strip()
    if not cleaned:
        return FALLBACK_FILENAME
    return cleaned[:MAX_FILENAME_LENGTH]

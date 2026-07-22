"""Masking of sensitive identifiers.

National identifiers (IIN/BIN) are personal data. By default they are masked in API responses,
events, and logs; the full value is stored and disclosed only to authorized roles (docs/06, Q-D3).
"""

from __future__ import annotations

# Number of trailing characters left visible when masking an identifier.
_VISIBLE_TAIL = 4


def mask_identifier(value: str | None) -> str | None:
    """Mask a national identifier, revealing only its trailing characters.

    Args:
        value: The full identifier, or ``None``.

    Returns:
        The masked identifier (all but the last few characters replaced with ``*``), or ``None``
        when the input is ``None``. Values no longer than the visible tail are fully masked.
    """
    if value is None:
        return None
    stripped = value.strip()
    if len(stripped) <= _VISIBLE_TAIL:
        return "*" * len(stripped)
    return "*" * (len(stripped) - _VISIBLE_TAIL) + stripped[-_VISIBLE_TAIL:]

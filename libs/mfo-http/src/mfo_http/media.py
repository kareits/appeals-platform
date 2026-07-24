"""Exact JSON media-type validation shared across service trust boundaries.

A single parser keeps every gateway/relay path fail-closed in the same way: a downstream response is
trusted as JSON only when its ``Content-Type`` names exactly ``application/json`` (optionally with
parameters such as ``charset``). Substring checks are deliberately avoided because they accept
near-misses like ``application/jsonp`` and ``text/application/json`` that are not JSON
(CR-BFF-R6-MEDIUM-003).
"""

from __future__ import annotations

_JSON_MEDIA_TYPE = "application/json"


def is_json_media_type(content_type: str | None, *, allow_structured_suffix: bool = False) -> bool:
    """Return whether a ``Content-Type`` header denotes JSON under an exact, case-insensitive match.

    The media type is the part before the first ``;``; surrounding whitespace and letter case are
    normalized, so ``application/json``, ``Application/JSON`` and ``application/json; charset=utf8``
    all match. Near-misses like ``application/jsonp`` and ``text/application/json`` never match.
    The structured ``application/*+json`` suffix is accepted only when a caller explicitly opts in;
    it is never enabled implicitly.

    Args:
        content_type: The raw ``Content-Type`` header value, or ``None`` when absent.
        allow_structured_suffix: When true, also accept an ``application/<x>+json`` media type.

    Returns:
        ``True`` when the media type denotes JSON under the configured policy.
    """
    if not content_type:
        return False
    main = content_type.split(";", 1)[0].strip().lower()
    if main == _JSON_MEDIA_TYPE:
        return True
    if allow_structured_suffix and main.startswith("application/") and main.endswith("+json"):
        return True
    return False

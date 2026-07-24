"""Tests for the exact JSON media-type parser shared across trust boundaries."""

from __future__ import annotations

import pytest
from mfo_http import is_json_media_type


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "application/json;charset=utf-8",
        "  application/json  ",
        "Application/JSON",
        "APPLICATION/JSON; charset=UTF-8",
    ],
)
def test_accepts_exact_json_with_parameters_and_casing(content_type: str) -> None:
    """An exact ``application/json`` media type is accepted regardless of casing/parameters."""
    assert is_json_media_type(content_type) is True


@pytest.mark.parametrize(
    "content_type",
    [
        None,
        "",
        "application/jsonp",
        "text/application/json",
        "text/plain",
        "application/json-patch",
        "application/xml",
        "application/vnd.api+json",
    ],
)
def test_rejects_near_misses_and_missing(content_type: str | None) -> None:
    """Near-miss and missing media types are rejected under the default (strict) policy."""
    assert is_json_media_type(content_type) is False


def test_structured_suffix_is_opt_in_only() -> None:
    """The ``application/*+json`` structured suffix is accepted only when explicitly enabled."""
    assert is_json_media_type("application/vnd.api+json") is False
    assert is_json_media_type("application/vnd.api+json", allow_structured_suffix=True) is True
    # Even with the opt-in, a non-application top-level type is still rejected.
    assert is_json_media_type("text/vnd.api+json", allow_structured_suffix=True) is False

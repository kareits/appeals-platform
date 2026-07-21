"""Shared testing helpers for platform services.

Exposes an ASGI test-client factory and JSON-Schema contract assertions. The scope is bounded by
ADR-007 (technical test support only).
"""

from mfo_testing.asgi import create_asgi_client
from mfo_testing.contracts import assert_matches_schema

__all__ = [
    "assert_matches_schema",
    "create_asgi_client",
]

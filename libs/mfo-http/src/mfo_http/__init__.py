"""Shared HTTP support for platform services.

Exposes RFC 7807 Problem Details error handling, correlation-ID middleware, and an HTTP client
wrapper. The scope is bounded by ADR-007 (no domain or business logic).
"""

from mfo_http.bounded import BoundedResponse, read_bounded
from mfo_http.client import PlatformHttpClient
from mfo_http.errors import ProblemDetail, ProblemDetailError, install_problem_detail_handlers
from mfo_http.media import is_json_media_type
from mfo_http.middleware import CorrelationIdMiddleware

__all__ = [
    "BoundedResponse",
    "CorrelationIdMiddleware",
    "PlatformHttpClient",
    "ProblemDetail",
    "ProblemDetailError",
    "install_problem_detail_handlers",
    "is_json_media_type",
    "read_bounded",
]

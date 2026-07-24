"""Safe relay, bounded I/O, and error-normalization helpers for the gateway.

The gateway forwards ticket command/search and login requests to their owning services, but it does
not blindly echo downstream responses to the public client (CR-BFF-HIGH-002), and it never buffers
an unbounded request or response before enforcing a size limit (CR-BFF-R6-HIGH-001):

- incoming request bodies are read incrementally and rejected with ``413`` before full buffering;
- downstream responses are streamed under a hard byte ceiling via the shared bounded-read helper;
- successful JSON responses are relayed (bounded in size, exact ``application/json`` media type);
- documented client-error statuses are relayed as sanitized RFC 7807 Problem Details reconstructed
  from allowed fields only, so internal URLs, stack traces, SQL, or HTML never cross the boundary;
- any 5xx, unexpected status, unexpected media type, oversized, or malformed body becomes a safe
  gateway 502; a downstream timeout becomes a 504 and a connection failure a 503;
- only an explicit allowlist of protocol headers is propagated (``WWW-Authenticate``,
  ``Retry-After``, ``Location``, ``ETag``).

The correlation ID is added to every response by the correlation middleware.
"""

from __future__ import annotations

import json

import httpx
from mfo_http import BoundedResponse, ProblemDetail, is_json_media_type
from starlette.requests import Request
from starlette.responses import Response

PROBLEM_CONTENT_TYPE = "application/problem+json"

# Downstream client-error statuses whose semantics the gateway preserves (as sanitized Problem
# Details). Any other non-2xx status (notably 5xx) is normalized to a safe gateway error.
_RELAYABLE_CLIENT_ERRORS = frozenset({400, 401, 403, 404, 405, 409, 412, 415, 422, 429})

# Protocol-significant response headers propagated from the downstream (case-insensitive match).
_SEMANTIC_HEADERS = ("www-authenticate", "retry-after", "location", "etag")

# Generic, non-leaking titles used when a downstream error body is absent or untrusted.
_STATUS_TITLES = {
    400: "Bad request",
    401: "Not authenticated",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    412: "Precondition failed",
    415: "Unsupported media type",
    422: "Unprocessable entity",
    429: "Too many requests",
}


class PayloadTooLargeError(Exception):
    """Raised when an incoming request body exceeds the ingress ceiling (mapped to ``413``)."""


async def read_body_bounded(request: Request, max_bytes: int) -> bytes:
    """Read an incoming request body incrementally, rejecting it before it exceeds a byte ceiling.

    The body is consumed chunk by chunk from the ASGI stream, so an oversized body (whether it
    advertises a large ``Content-Length`` or streams chunked without one) is rejected the moment the
    cumulative size crosses ``max_bytes`` — never fully buffered, and never forwarded downstream
    (CR-BFF-R6-HIGH-001). A ``Content-Length`` already over the ceiling is rejected up front.

    Args:
        request: The incoming request whose body is read.
        max_bytes: The maximum number of body bytes to accept.

    Returns:
        The fully read body, guaranteed to be at most ``max_bytes`` bytes.

    Raises:
        PayloadTooLargeError: When the body exceeds ``max_bytes``.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                raise PayloadTooLargeError
        except ValueError:
            # A malformed Content-Length is ignored; the incremental ceiling below still applies.
            pass
    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError
        chunks.append(chunk)
    return b"".join(chunks)


def _passthrough_headers(headers: httpx.Headers) -> dict[str, str]:
    """Copy only the allowlisted protocol headers from a downstream response.

    Args:
        headers: The downstream response headers.

    Returns:
        The subset of headers safe to propagate.
    """
    out: dict[str, str] = {}
    for name in _SEMANTIC_HEADERS:
        value = headers.get(name)
        if value is not None:
            # Strip CR/LF to prevent header injection via a crafted downstream value.
            out[name.title()] = value.replace("\r", "").replace("\n", "")
    return out


def _problem_body(problem: ProblemDetail) -> bytes:
    """Serialize a Problem Details payload to JSON bytes.

    Args:
        problem: The problem details.

    Returns:
        The encoded body.
    """
    return json.dumps(problem.to_dict()).encode("utf-8")


def _sanitized_problem(status: int) -> ProblemDetail:
    """Build a safe RFC 7807 Problem Details for a relayed downstream client-error status.

    Free-form downstream ``title``/``detail`` text is **not** copied: a validation or domain service
    can accidentally include SQL, hostnames, URLs, exception text, or regulated values in those
    fields, so the gateway substitutes its own safe, status-derived title and no detail
    (CR-BFF-RR-HIGH-003). Only the status semantics cross the boundary.

    Args:
        status: The status code to report.

    Returns:
        The safe problem details.
    """
    return ProblemDetail(title=_STATUS_TITLES.get(status, "Request failed"), status=status)


def _problem_response(problem: ProblemDetail, headers: dict[str, str]) -> Response:
    """Build a Problem Details response with the given propagated headers.

    Args:
        problem: The problem details.
        headers: The allowlisted headers to attach.

    Returns:
        The Problem Details response.
    """
    return Response(
        content=_problem_body(problem),
        status_code=problem.status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def _gateway_error(status: int, detail: str, headers: dict[str, str]) -> Response:
    """Build a safe gateway Problem Details (used for 5xx/unexpected/transport downstream failures).

    Args:
        status: The gateway status (typically 502/503/504).
        detail: A safe, non-leaking detail.
        headers: The allowlisted headers to attach.

    Returns:
        The Problem Details response.
    """
    titles = {502: "Bad gateway", 503: "Upstream unavailable", 504: "Upstream timeout"}
    title = titles.get(status, "Gateway error")
    return _problem_response(ProblemDetail(title=title, status=status, detail=detail), headers)


def payload_too_large_response() -> Response:
    """Build the sanitized RFC 7807 ``413`` response for an oversized ingress body.

    Returns:
        The Problem Details response (the correlation ID is added by the middleware).
    """
    return _problem_response(
        ProblemDetail(
            title="Payload too large",
            status=413,
            detail="the request body exceeded the maximum allowed size",
        ),
        {},
    )


def relay(bounded: BoundedResponse, service: str) -> Response:
    """Relay a bounded downstream response to the client under the gateway response policy.

    Args:
        bounded: The settled bounded downstream read.
        service: The downstream service name used in transport-failure details.

    Returns:
        A safe response: relayed JSON on success, sanitized Problem Details on documented client
        errors, a 504/503 on downstream timeout/connection failure, or a gateway 502 for
        5xx/unexpected/oversized/malformed responses.
    """
    if bounded.failure == "timeout":
        return _gateway_error(504, f"the {service} service timed out", {})
    if bounded.failure == "connection":
        return _gateway_error(503, f"the {service} service is unreachable", {})

    assert bounded.status is not None
    headers = _passthrough_headers(bounded.headers)
    status = bounded.status

    if bounded.oversized:
        return _gateway_error(502, "the upstream response was too large", headers)

    if 200 <= status < 300:
        if not is_json_media_type(bounded.headers.get("content-type")):
            return _gateway_error(502, "the upstream returned an unexpected response", headers)
        body = bounded.content or b""
        try:
            json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _gateway_error(502, "the upstream returned a malformed response", headers)
        return Response(
            content=body,
            status_code=status,
            media_type="application/json",
            headers=headers,
        )

    if status in _RELAYABLE_CLIENT_ERRORS:
        return _problem_response(_sanitized_problem(status), headers)

    # 5xx and any other unexpected status: never leak the body.
    return _gateway_error(502, "the upstream service returned an error", headers)


def forward_headers(token: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    """Build the headers forwarded on a downstream ticket call.

    The caller's bearer token is forwarded so the downstream service enforces its own authorization;
    the correlation ID is added automatically by the platform HTTP client.

    Args:
        token: The caller's bearer access token.
        idempotency_key: Optional idempotency key to forward (registration only).

    Returns:
        The headers to send downstream.
    """
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers

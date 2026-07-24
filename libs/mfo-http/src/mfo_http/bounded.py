"""Bounded, streaming downstream reads shared by every service-to-service call.

A single helper enforces one resource policy for the whole platform: a downstream response body is
read incrementally and abandoned the instant it crosses a byte ceiling, so a faulty or hostile
downstream can never make the caller buffer an unbounded body before a size check
(CR-BFF-R6-HIGH-001). Only 2xx bodies are buffered (callers relay/parse those); non-2xx responses
return status and headers with the body left unread and the stream closed, because error bodies are
never trusted or relayed verbatim. Expected transport failures are reported as ``timeout``/
``connection`` rather than raised; cancellation and programming errors propagate unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from mfo_http.client import PlatformHttpClient


@dataclass(frozen=True)
class BoundedResponse:
    """The settled outcome of a bounded, streamed downstream read.

    Attributes:
        status: The downstream status code, or ``None`` when the transport failed.
        headers: The downstream response headers (empty on a transport failure).
        content: The buffered body on a bounded 2xx, or ``None`` (non-2xx, oversized, or failure).
        oversized: ``True`` when a 2xx body exceeded the ceiling and was abandoned unbuffered.
        failure: ``"timeout"`` or ``"connection"`` on a transport failure, otherwise ``None``.
    """

    status: int | None
    headers: httpx.Headers
    content: bytes | None
    oversized: bool
    failure: str | None


async def read_bounded(
    client: PlatformHttpClient,
    method: str,
    url: str,
    *,
    max_bytes: int,
    **stream_kwargs: object,
) -> BoundedResponse:
    """Stream a downstream request, buffering a 2xx body only up to a hard byte ceiling.

    The body is pulled chunk by chunk; the moment the cumulative size exceeds ``max_bytes`` the read
    stops, the remaining chunks are not pulled, the stream is closed by the context manager, and the
    result is flagged ``oversized`` with no body retained. Non-2xx responses are returned without
    reading the body at all.

    Args:
        client: The platform HTTP client (injects the correlation header on the streamed request).
        method: The HTTP method.
        url: The request URL or path relative to the client base URL.
        max_bytes: The maximum number of body bytes to buffer on a 2xx response.
        **stream_kwargs: Extra arguments forwarded to the streaming request (headers, params,
            content, ...).

    Returns:
        The settled bounded response.
    """
    try:
        async with client.stream(method, url, **stream_kwargs) as response:
            status = response.status_code
            headers = response.headers
            if not (200 <= status < 300):
                # Error bodies are never trusted or relayed; do not buffer them.
                return BoundedResponse(status, headers, None, False, None)
            total = 0
            chunks: list[bytes] = []
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    return BoundedResponse(status, headers, None, True, None)
                chunks.append(chunk)
            return BoundedResponse(status, headers, b"".join(chunks), False, None)
    except httpx.TimeoutException:
        return BoundedResponse(None, httpx.Headers(), None, False, "timeout")
    except httpx.RequestError:
        return BoundedResponse(None, httpx.Headers(), None, False, "connection")

"""An HTTP client wrapper that propagates the correlation ID.

Wraps ``httpx.AsyncClient`` so outbound service-to-service calls carry the current correlation ID
and a sensible default timeout, keeping cross-service tracing consistent.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any

import httpx
from mfo_observability.correlation import CORRELATION_ID_HEADER, get_correlation_id

DEFAULT_TIMEOUT_SECONDS = 10.0
"""Default request timeout applied when the caller does not specify one."""


class PlatformHttpClient:
    """An async HTTP client that injects the correlation ID into every request."""

    def __init__(
        self,
        base_url: str = "",
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: An optional base URL prepended to request paths.
            timeout: The default request timeout — a float (seconds) or a fine-grained
                ``httpx.Timeout`` (connect/read/write/pool).
            client: An optional pre-configured ``httpx.AsyncClient`` (useful for testing).
        """
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send an HTTP request with the correlation header attached.

        Args:
            method: The HTTP method (for example, ``"GET"``).
            url: The request URL or path relative to the base URL.
            **kwargs: Additional arguments forwarded to ``httpx.AsyncClient.request``.

        Returns:
            The HTTP response.
        """
        headers = dict(kwargs.pop("headers", {}) or {})
        correlation_id = get_correlation_id()
        if correlation_id is not None:
            headers.setdefault(CORRELATION_ID_HEADER, correlation_id)
        return await self._client.request(method, url, headers=headers, **kwargs)

    def stream(
        self, method: str, url: str, **kwargs: Any
    ) -> AbstractAsyncContextManager[httpx.Response]:
        """Open a streaming request with the correlation header attached.

        Used to read a response incrementally (for example, to enforce a hard byte ceiling before
        the whole body is buffered). Use as ``async with client.stream(...) as response: ...``.

        Args:
            method: The HTTP method.
            url: The request URL or path relative to the base URL.
            **kwargs: Additional arguments forwarded to ``httpx.AsyncClient.stream``.

        Returns:
            An async context manager yielding the streaming response.
        """
        headers = dict(kwargs.pop("headers", {}) or {})
        correlation_id = get_correlation_id()
        if correlation_id is not None:
            headers.setdefault(CORRELATION_ID_HEADER, correlation_id)
        return self._client.stream(method, url, headers=headers, **kwargs)

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release its connections."""
        await self._client.aclose()

    async def __aenter__(self) -> PlatformHttpClient:
        """Enter the async context manager.

        Returns:
            This client instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the async context manager and close the client.

        Args:
            exc_type: The exception type raised in the context, if any.
            exc: The exception instance, if any.
            traceback: The traceback, if any.
        """
        await self.aclose()

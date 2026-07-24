"""Tests for the shared bounded, streaming downstream read.

A custom counting :class:`httpx.AsyncByteStream` proves that ``read_bounded`` stops pulling the body
the instant the ceiling is crossed, never buffers an oversized body, closes the stream, propagates
cancellation, maps transport failures, and forwards the correlation ID (CR-BFF-R6-HIGH-001).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from mfo_http import PlatformHttpClient, read_bounded
from mfo_observability.correlation import CORRELATION_ID_HEADER, set_correlation_id

_LIMIT = 1_000_000

_ResponseFactory = Callable[[httpx.Request], httpx.Response]


class _CountingStream(httpx.AsyncByteStream):
    """An async byte stream that counts yielded chunks and records closure.

    Attributes:
        yielded: The number of chunks actually pulled by the consumer.
        closed: Whether ``aclose`` was called.
    """

    def __init__(self, chunk: bytes, count: int, *, fail_with: type[BaseException] | None = None):
        """Initialize the stream.

        Args:
            chunk: The byte chunk emitted on each iteration.
            count: How many chunks to emit before stopping.
            fail_with: An exception type to raise mid-stream after the first chunk, or ``None``.
        """
        self._chunk = chunk
        self._count = count
        self._fail_with = fail_with
        self.yielded = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield the configured chunks, optionally failing mid-stream.

        Yields:
            The next byte chunk.

        Raises:
            BaseException: The configured ``fail_with`` type, after the first chunk.
        """
        for index in range(self._count):
            if self._fail_with is not None and index == 1:
                raise self._fail_with("stream failed mid-flight")
            self.yielded += 1
            yield self._chunk

    async def aclose(self) -> None:
        """Record that the consumer closed the stream."""
        self.closed = True


def _client(
    response_factory: _ResponseFactory,
) -> tuple[PlatformHttpClient, dict[str, str | None]]:
    """Build a client whose mock transport serves a response and captures the correlation header.

    Args:
        response_factory: A callable returning the ``httpx.Response`` to serve.

    Returns:
        The client and a mapping updated with the forwarded correlation header.
    """
    captured: dict[str, str | None] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve the configured response and capture the correlation header.

        Args:
            request: The incoming request.

        Returns:
            The configured response.
        """
        captured["correlation"] = request.headers.get(CORRELATION_ID_HEADER)
        return response_factory(request)

    client = PlatformHttpClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler), base_url="http://svc")
    )
    return client, captured


async def test_reads_body_of_exactly_the_ceiling() -> None:
    """A 2xx body of exactly the ceiling is fully buffered."""
    stream = _CountingStream(b"y" * 500_000, 2)  # total == _LIMIT
    client, _ = _client(
        lambda r: httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)
    )
    try:
        result = await read_bounded(client, "GET", "/x", max_bytes=_LIMIT)
    finally:
        await client.aclose()
    assert result.failure is None
    assert result.oversized is False
    assert result.content is not None
    assert len(result.content) == _LIMIT
    assert stream.yielded == 2


async def test_rejects_one_byte_over_the_ceiling() -> None:
    """A single chunk one byte over the ceiling is abandoned as oversized."""
    stream = _CountingStream(b"z" * (_LIMIT + 1), 1)
    client, _ = _client(
        lambda r: httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)
    )
    try:
        result = await read_bounded(client, "GET", "/x", max_bytes=_LIMIT)
    finally:
        await client.aclose()
    assert result.oversized is True
    assert result.content is None
    assert stream.yielded == 1
    assert stream.closed is True


async def test_stops_early_and_closes_on_oversized_stream() -> None:
    """A large stream stops right after the ceiling, leaves the rest unread, and is closed."""
    set_correlation_id("corr-xyz")
    stream = _CountingStream(b"a" * 100_000, 100)  # 10 MB, far above the ceiling
    client, captured = _client(
        lambda r: httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)
    )
    try:
        result = await read_bounded(client, "GET", "/x", max_bytes=_LIMIT)
    finally:
        await client.aclose()
    assert result.oversized is True
    assert result.content is None
    assert stream.yielded == (_LIMIT // 100_000) + 1
    assert stream.yielded < 100  # remaining chunks were never pulled
    assert stream.closed is True
    assert captured["correlation"] == "corr-xyz"


async def test_non_2xx_body_is_not_buffered() -> None:
    """A non-2xx response returns status and headers without reading the body."""
    stream = _CountingStream(b"a" * 100_000, 100)
    client, _ = _client(
        lambda r: httpx.Response(500, headers={"content-type": "text/html"}, stream=stream)
    )
    try:
        result = await read_bounded(client, "GET", "/x", max_bytes=_LIMIT)
    finally:
        await client.aclose()
    assert result.status == 500
    assert result.content is None
    assert result.oversized is False
    assert stream.yielded == 0  # the error body was never pulled


async def test_maps_timeout_and_connection_failures() -> None:
    """Transport timeout and connection failures are reported, not raised."""

    def _timeout(request: httpx.Request) -> httpx.Response:
        """Raise a read timeout.

        Args:
            request: The incoming request.

        Raises:
            httpx.ReadTimeout: Always.
        """
        raise httpx.ReadTimeout("timed out", request=request)

    def _connect(request: httpx.Request) -> httpx.Response:
        """Raise a connect error.

        Args:
            request: The incoming request.

        Raises:
            httpx.ConnectError: Always.
        """
        raise httpx.ConnectError("refused", request=request)

    client_t, _ = _client(_timeout)
    client_c, _ = _client(_connect)
    try:
        assert (await read_bounded(client_t, "GET", "/x", max_bytes=_LIMIT)).failure == "timeout"
        assert (await read_bounded(client_c, "GET", "/x", max_bytes=_LIMIT)).failure == "connection"
    finally:
        await client_t.aclose()
        await client_c.aclose()


async def test_does_not_swallow_cancellation() -> None:
    """Cancellation propagates out of the read; it is never converted into a settled result."""
    stream = _CountingStream(b"a" * 1_000, 5, fail_with=asyncio.CancelledError)
    client, _ = _client(
        lambda r: httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await read_bounded(client, "GET", "/x", max_bytes=_LIMIT)
    finally:
        await client.aclose()
    assert stream.closed is True

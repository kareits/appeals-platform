"""Byte-ceiling streaming tests for the workspace downstream reads.

The oversized-body protection must stop pulling the response the moment the byte ceiling is crossed,
never assemble the full body in memory, and release the stream — a pre-buffered ``httpx.Response``
cannot prove any of that (CR-BFF-R5-MEDIUM-002). These white-box tests drive the private ``_read``
helper with a custom :class:`httpx.AsyncByteStream` that counts the chunks it actually yields and
records ``aclose``, so early termination, non-buffering, resource release, correlation propagation
and cancellation-safety are all asserted directly, with the byte-ceiling boundary conditions.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from bff_service.application.workspace import (
    SectionStatus,
    WorkspaceUpstreamError,
    _classify_card,
    _classify_comments,
    _read,
)
from mfo_http import PlatformHttpClient
from mfo_observability.correlation import CORRELATION_ID_HEADER, set_correlation_id

_LIMIT = 2_000_000


class _CountingStream(httpx.AsyncByteStream):
    """An async byte stream that counts yielded chunks and records closure.

    Attributes:
        yielded: The number of chunks actually pulled by the consumer.
        closed: Whether ``aclose`` was called (the consumer released the stream).
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


def _client(stream: _CountingStream, captured: dict[str, str | None]) -> PlatformHttpClient:
    """Build an HTTP client whose mock transport serves a streaming JSON response.

    Args:
        stream: The counting stream to serve as the response body.
        captured: A mapping updated with the forwarded correlation header.

    Returns:
        A platform HTTP client bound to the mock transport.
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        """Return a streaming 200 response and capture the correlation header.

        Args:
            request: The incoming request.

        Returns:
            A streaming JSON response.
        """
        captured["correlation"] = request.headers.get(CORRELATION_ID_HEADER)
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)

    return PlatformHttpClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler), base_url="http://ticket")
    )


async def test_read_stops_early_and_closes_on_oversized_stream() -> None:
    """An oversized stream stops right after the ceiling, buffers nothing, and is closed."""
    set_correlation_id("corr-123")
    # 100 chunks of 100 KB = 10 MB, far above the 2 MB ceiling.
    stream = _CountingStream(b"x" * 100_000, 100)
    captured: dict[str, str | None] = {}
    client = _client(stream, captured)
    try:
        read = await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()

    assert read.failure == "oversized"
    assert read.body is None  # the full body was never assembled in memory
    # Reading stops on the first chunk that crosses the ceiling; remaining chunks are not pulled.
    assert stream.yielded == (_LIMIT // 100_000) + 1
    assert stream.yielded < 100
    assert stream.closed is True
    assert captured["correlation"] == "corr-123"  # correlation still propagated downstream


async def test_oversized_card_maps_to_502_and_comments_degrade() -> None:
    """An oversized read is a card 502 and an optional-comments degradation, never trusted data."""
    stream = _CountingStream(b"x" * 100_000, 100)
    client = _client(stream, {})
    try:
        read = await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()

    with pytest.raises(WorkspaceUpstreamError) as excinfo:
        _classify_card(read)
    assert excinfo.value.status == 502
    assert _classify_comments(read).status is SectionStatus.UNAVAILABLE


async def test_read_allows_body_of_exactly_the_ceiling() -> None:
    """A body of exactly the ceiling is fully read; the limit is not off-by-one strict."""
    stream = _CountingStream(b"y" * 1_000_000, 2)  # total == _LIMIT
    client = _client(stream, {})
    try:
        read = await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()

    assert read.failure is None
    assert read.body is not None
    assert len(read.body) == _LIMIT
    assert stream.yielded == 2  # the whole body was consumed


async def test_read_rejects_one_byte_over_the_ceiling_in_a_single_chunk() -> None:
    """A single chunk one byte over the ceiling is rejected as oversized."""
    stream = _CountingStream(b"z" * (_LIMIT + 1), 1)
    client = _client(stream, {})
    try:
        read = await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()

    assert read.failure == "oversized"
    assert read.body is None
    assert stream.yielded == 1
    assert stream.closed is True


async def test_read_returns_invalid_utf8_body_for_the_classifier_to_reject() -> None:
    """A small invalid-UTF-8 body is read within the ceiling and rejected as a 502 by the card."""
    stream = _CountingStream(b"\xff\xfe\x00", 1)
    client = _client(stream, {})
    try:
        read = await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()

    assert read.failure is None
    assert read.body == b"\xff\xfe\x00"
    with pytest.raises(WorkspaceUpstreamError) as excinfo:
        _classify_card(read)
    assert excinfo.value.status == 502


async def test_read_maps_premature_transport_error_to_connection_failure() -> None:
    """A stream that errors mid-flight degrades to a connection failure, not a partial body."""
    stream = _CountingStream(b"a" * 1_000, 5, fail_with=httpx.ReadError)
    client = _client(stream, {})
    try:
        read = await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()

    assert read.failure == "connection"
    assert read.body is None
    assert stream.closed is True


async def test_read_does_not_swallow_cancellation() -> None:
    """Cancellation propagates out of the read; it is never converted into a partial success."""
    stream = _CountingStream(b"a" * 1_000, 5, fail_with=asyncio.CancelledError)
    client = _client(stream, {})
    try:
        with pytest.raises(asyncio.CancelledError):
            await _read(client, "/api/v1/tickets/x", "tok", _LIMIT)
    finally:
        await client.aclose()
    assert stream.closed is True

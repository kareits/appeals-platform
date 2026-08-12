"""Unit tests for storage keys and the local filesystem adapter.

Covers the two security properties the storage layer owns (docs/06): keys are random and never
derived from client input, and no key can address a path outside the storage root.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from document_service.domain.storage import (
    STORAGE_KEY_PATTERN,
    StorageKeyError,
    StorageLimitExceededError,
    StoredObjectMissingError,
    generate_storage_key,
    validate_storage_key,
)
from document_service.infrastructure.local_storage import LocalFileStorage


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    """Yield the given byte parts as an async stream.

    Args:
        *parts: The chunks to yield.

    Yields:
        Each chunk in order.
    """
    for part in parts:
        yield part


async def _collect(stream: AsyncIterator[bytes]) -> bytes:
    """Read an async byte stream into a single value.

    Args:
        stream: The stream to drain.

    Returns:
        The concatenated bytes.
    """
    return b"".join([chunk async for chunk in stream])


def test_generated_keys_match_the_pattern_and_are_unique() -> None:
    """Keys carry a date prefix, 128 random bits, and never repeat."""
    moment = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    keys = {generate_storage_key(moment) for _ in range(200)}
    assert len(keys) == 200
    for key in keys:
        assert STORAGE_KEY_PATTERN.match(key)
        assert key.startswith("2026/08/")


def test_generated_key_carries_no_extension() -> None:
    """A key never ends in a file extension, so it cannot be interpreted by name."""
    assert "." not in generate_storage_key(datetime(2026, 1, 5, tzinfo=UTC))


@pytest.mark.parametrize(
    "key",
    [
        "../../etc/passwd",
        "2026/08/../../../etc/passwd",
        "/etc/passwd",
        "2026\\08\\abcd",
        "2026/08/NOTHEX0000000000000000000000000",
        "2026/08/" + "a" * 31,
        "2026/8/" + "a" * 32,
        "",
    ],
)
def test_malformed_keys_are_rejected(key: str) -> None:
    """Traversal sequences, absolute paths, and wrong shapes never become a path."""
    with pytest.raises(StorageKeyError):
        validate_storage_key(key)


async def test_save_read_exists_and_delete_round_trip(tmp_path: Path) -> None:
    """Content written under a key can be found, streamed back, and removed."""
    storage = LocalFileStorage(tmp_path / "storage")
    key = generate_storage_key(datetime.now(UTC))

    written = await storage.save(key, _chunks(b"hello ", b"world"), 1024)

    assert written == 11
    assert await storage.exists(key) is True
    assert await _collect(await storage.open_stream(key)) == b"hello world"

    await storage.delete(key)
    assert await storage.exists(key) is False
    # Deleting an absent object is a no-op, so cleanup paths are safe to run twice.
    await storage.delete(key)


async def test_storage_stays_inside_its_root(tmp_path: Path) -> None:
    """A traversal key is refused before any path outside the root is touched."""
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"secret")
    storage = LocalFileStorage(tmp_path / "storage")

    with pytest.raises(StorageKeyError):
        await storage.save("../outside.txt", _chunks(b"overwritten"), 1024)
    with pytest.raises(StorageKeyError):
        await storage.open_stream("../outside.txt")

    assert outside.read_bytes() == b"secret"


async def test_oversized_upload_is_rejected_and_leaves_no_object(tmp_path: Path) -> None:
    """Exceeding the limit aborts the write and discards the partial object."""
    storage = LocalFileStorage(tmp_path / "storage")
    key = generate_storage_key(datetime.now(UTC))

    with pytest.raises(StorageLimitExceededError):
        await storage.save(key, _chunks(b"a" * 8, b"b" * 8), 10)

    assert await storage.exists(key) is False


async def test_failing_stream_leaves_no_object(tmp_path: Path) -> None:
    """A producer error mid-upload removes the partial object rather than keeping it."""
    storage = LocalFileStorage(tmp_path / "storage")
    key = generate_storage_key(datetime.now(UTC))

    async def _failing() -> AsyncIterator[bytes]:
        """Yield one chunk and then fail.

        Yields:
            A single chunk before raising.

        Raises:
            RuntimeError: Always, after the first chunk.
        """
        yield b"partial"
        raise RuntimeError("client disconnected")

    with pytest.raises(RuntimeError):
        await storage.save(key, _failing(), 1024)

    assert await storage.exists(key) is False


async def test_missing_object_is_reported(tmp_path: Path) -> None:
    """Reading a key with no stored object raises rather than returning empty content."""
    storage = LocalFileStorage(tmp_path / "storage")
    with pytest.raises(StoredObjectMissingError):
        await storage.open_stream(generate_storage_key(datetime.now(UTC)))


def test_storage_root_is_created(tmp_path: Path) -> None:
    """The adapter provisions its root, so a fresh volume needs no manual preparation."""
    root = tmp_path / "nested" / "storage"
    storage = LocalFileStorage(root)
    assert root.is_dir()
    assert storage.backend_name == "local"

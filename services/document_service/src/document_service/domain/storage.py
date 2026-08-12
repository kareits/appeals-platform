"""The file-storage port and the rules that make a storage key safe.

The document service is the only component that touches stored bytes, and it reaches them through
this port rather than the filesystem API directly (ADR-014): the MVP binds it to a local filesystem
adapter, and a GridFS or corporate Document API adapter can be added later without changing document
identifiers or the HTTP contract.

Storage keys are generated here, never derived from client input: an object's location is random and
unguessable, so a crafted filename cannot select or overwrite an existing object, and a leaked key
carries no business meaning (docs/06 "random storage key", "path traversal protection"). Keys are
also validated on the way *in* to an adapter, so a malformed key from a corrupted metadata row can
never be turned into a path outside the storage root.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol, runtime_checkable

# A key is exactly ``YYYY/MM/<32 lowercase hex chars>``. The date prefix keeps directories from
# growing without bound; the random component is 128 bits. Deliberately carries no file extension:
# the stored object is never interpreted by its name, so a ".php"/".html" suffix cannot be used to
# influence any server that later serves the directory.
STORAGE_KEY_PATTERN = re.compile(r"^\d{4}/\d{2}/[0-9a-f]{32}$")

# Bytes read per chunk when streaming to and from storage. Large enough to keep syscall overhead
# low, small enough that a request never buffers a whole document in memory.
STREAM_CHUNK_SIZE = 64 * 1024


class StorageKeyError(ValueError):
    """Raised when a storage key is malformed and must not be turned into a path."""


class StorageLimitExceededError(Exception):
    """Raised when an upload exceeds the configured size limit.

    The adapter discards whatever it has already written before raising, so a rejected upload leaves
    no partial object behind.
    """


class StoredObjectMissingError(Exception):
    """Raised when metadata references an object the backend cannot find.

    This means metadata and storage have diverged (for example, a file removed out of band); the API
    maps it to a server error rather than to "not found", because the document record does exist.
    """


def generate_storage_key(moment: datetime) -> str:
    """Generate a random, unguessable storage key under a date prefix.

    Args:
        moment: The timestamp whose year and month form the key prefix (UTC by convention).

    Returns:
        A key of the form ``YYYY/MM/<32 hex chars>``, matching :data:`STORAGE_KEY_PATTERN`.
    """
    return f"{moment.year:04d}/{moment.month:02d}/{secrets.token_hex(16)}"


def validate_storage_key(key: str) -> str:
    """Validate that a storage key is well formed before it is used to build a path.

    Args:
        key: The candidate storage key.

    Returns:
        The validated key.

    Raises:
        StorageKeyError: If the key does not match :data:`STORAGE_KEY_PATTERN`. Traversal sequences,
            absolute paths, backslashes, and unexpected characters all fail here.
    """
    if not STORAGE_KEY_PATTERN.match(key):
        raise StorageKeyError(f"invalid storage key: {key!r}")
    return key


@runtime_checkable
class FileStorage(Protocol):
    """A backend that stores and streams document bytes.

    Implementations must treat the storage key as an opaque identifier validated by
    :func:`validate_storage_key`, must never derive a location from a client-supplied filename, and
    must never let a key escape their own storage root. Content hashing and verification are added
    with TASK_03A-2.
    """

    @property
    def backend_name(self) -> str:
        """Return the backend identifier recorded on each document (for example, ``local``).

        Returns:
            The backend name stored in document metadata (ADR-014).
        """
        ...

    async def save(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int:
        """Store a stream of bytes under a key and return the number of bytes written.

        Args:
            key: The storage key to write to.
            chunks: The content, as an async iterator of byte chunks.
            max_bytes: The maximum number of bytes accepted.

        Returns:
            The number of bytes written.

        Raises:
            StorageKeyError: If the key is malformed.
            StorageLimitExceededError: If the content exceeds ``max_bytes``; any partial object is
                removed before raising.
        """
        ...

    async def open_stream(self, key: str) -> AsyncIterator[bytes]:
        """Open a stored object for streaming reads.

        Args:
            key: The storage key to read.

        Returns:
            An async iterator over the stored bytes.

        Raises:
            StorageKeyError: If the key is malformed.
            StoredObjectMissingError: If the object does not exist in the backend.
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove a stored object, ignoring an already-absent one.

        Args:
            key: The storage key to remove.

        Raises:
            StorageKeyError: If the key is malformed.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Report whether an object is present in the backend.

        Args:
            key: The storage key to check.

        Returns:
            ``True`` when the object exists.

        Raises:
            StorageKeyError: If the key is malformed.
        """
        ...

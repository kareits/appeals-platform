"""Application-layer errors for document use cases.

These are transport-agnostic; the API layer maps them to RFC 7807 Problem Details responses.
"""

from __future__ import annotations


class DocumentNotFoundError(Exception):
    """Raised when a referenced document does not exist or is soft-deleted (mapped to 404)."""


class DocumentNotAvailableError(Exception):
    """Raised when a document exists but its bytes must not be served (mapped to 409).

    Covers an in-flight or failed upload now, and — from TASK_03A-2 — a document awaiting or failing
    an antivirus verdict, which docs/06 requires to stay inaccessible until it is clean.

    Attributes:
        status: The document's current lifecycle status, for a non-disclosing message.
    """

    def __init__(self, status: str) -> None:
        """Initialize the error.

        Args:
            status: The document's current lifecycle status.
        """
        super().__init__(f"document is not available for download (status {status})")
        self.status = status


class DocumentAlreadyLinkedError(Exception):
    """Raised when linking would move a document to a different appeal (mapped to 409).

    Linkage is write-once evidence: silently re-pointing a stored document at another appeal would
    rewrite the regulatory record of what was attached where (docs/06). Re-linking to the same
    appeal is idempotent and does not raise.
    """


class UploadTooLargeError(Exception):
    """Raised when an upload exceeds the configured size limit (mapped to 413)."""


class StorageFailureError(Exception):
    """Raised when the storage backend fails or its object is missing (mapped to 500).

    The metadata row exists but the bytes could not be written or read, so the failure is a server-
    side inconsistency rather than a client error.
    """

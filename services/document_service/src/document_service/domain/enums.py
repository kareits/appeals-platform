"""Enumerations owned by the document service.

The values mirror the storage lifecycle listed in ``chatgpt_docs/services/DOCUMENT_SERVICE.md``. The
full set is declared here from the start so later phases add behavior, not new database types.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    """Storage lifecycle state of a document.

    TASK_03A-1 reaches only ``UPLOADING`` (bytes are being written), ``AVAILABLE`` (bytes are
    stored and downloadable), and ``UPLOAD_FAILED`` (writing failed; the metadata row is kept so the
    partial object is discoverable and never silently downloadable). ``PENDING_SCAN``/``CLEAN``/
    ``INFECTED`` become reachable when antivirus scanning is added in TASK_03A-2, ``UPLOADED`` when
    an intermediate handover step exists, and ``DELETED`` with soft deletion in EP-4.

    Attributes:
        UPLOADING: Bytes are being written; the document is not downloadable.
        UPLOADED: Bytes are written and awaiting the next lifecycle step (TASK_03A-2).
        PENDING_SCAN: Awaiting an antivirus verdict; not downloadable (TASK_03A-2, docs/06).
        CLEAN: The antivirus verdict is clean (TASK_03A-2).
        AVAILABLE: The document is stored and downloadable.
        INFECTED: The antivirus rejected the content; never downloadable (TASK_03A-2, docs/06).
        UPLOAD_FAILED: Writing the bytes failed; the object must not be served.
        DELETED: Soft-deleted; not downloadable and excluded from listings (EP-4).
    """

    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PENDING_SCAN = "PENDING_SCAN"
    CLEAN = "CLEAN"
    AVAILABLE = "AVAILABLE"
    INFECTED = "INFECTED"
    UPLOAD_FAILED = "UPLOAD_FAILED"
    DELETED = "DELETED"


# The only state whose bytes may be served. Kept as a named constant so the download gate is
# expressed once; TASK_03A-2 narrows how a document reaches it (scan first), not the gate itself.
DOWNLOADABLE_STATUSES: frozenset[DocumentStatus] = frozenset({DocumentStatus.AVAILABLE})

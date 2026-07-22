"""Internal identifier generation.

Internal surrogate keys use UUIDv7 (root ``CLAUDE.md``, ADR-003): a time-ordered UUID whose
leading bits encode a millisecond timestamp. Time ordering keeps primary-key inserts largely
sequential, which is friendlier to B-tree indexes than the random distribution of UUIDv4, while
remaining globally unique. The Python standard library does not yet expose ``uuid.uuid7`` on 3.12,
so a minimal RFC 9562-compliant generator is provided here (mirrors the ticket service).
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Generate a UUIDv7 (time-ordered) identifier.

    The layout follows RFC 9562: a 48-bit Unix millisecond timestamp, the 4-bit version, 12 random
    bits, the 2-bit variant, and 62 random bits.

    Returns:
        A version-7 UUID.
    """
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits (12 for rand_a, 62 for rand_b)

    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76  # version 7
    value |= ((rand >> 62) & 0xFFF) << 64  # 12 bits of rand_a
    value |= 0b10 << 62  # RFC 9562 variant
    value |= rand & 0x3FFFFFFFFFFFFFFF  # 62 bits of rand_b
    return uuid.UUID(int=value)

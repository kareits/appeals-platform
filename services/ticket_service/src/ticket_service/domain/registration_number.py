"""The business registration number value object.

The registration number is the human-facing, regulator-visible identifier of an appeal. It is
deliberately kept separate from the internal surrogate key (a UUID): the UUID is an implementation
detail used for foreign keys and idempotency, while the registration number is a stable business
artifact printed on correspondence and quoted by customers (root ``CLAUDE.md``, ADR-003).

Format: ``{PREFIX}-{YEAR}-{SEQUENCE}`` where the sequence is a zero-padded, per-year monotonic
counter, for example ``AP-2026-000001``. The prefix is configurable per deployment (ADR-016).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sequence numbers are zero-padded to this width. Six digits allow up to 999,999 appeals per year,
# comfortably above the expected volume; overflow widens the field rather than losing information.
_SEQUENCE_WIDTH = 6

# A prefix is a short uppercase token; the year is exactly four digits; the sequence is one or more
# digits (parsing tolerates widths beyond the default padding to stay forward compatible).
_PATTERN = re.compile(r"^(?P<prefix>[A-Z][A-Z0-9]*)-(?P<year>\d{4})-(?P<sequence>\d+)$")


@dataclass(frozen=True)
class RegistrationNumber:
    """An immutable, validated business registration number.

    Attributes:
        prefix: The uppercase deployment prefix (for example, ``AP``).
        year: The four-digit calendar year the number belongs to.
        sequence: The positive, per-year monotonic counter value.
    """

    prefix: str
    year: int
    sequence: int

    def __post_init__(self) -> None:
        """Validate the component parts.

        Raises:
            ValueError: If the prefix is not an uppercase token, the year is not four digits, or
                the sequence is not positive.
        """
        if not re.fullmatch(r"[A-Z][A-Z0-9]*", self.prefix):
            raise ValueError(f"prefix must be an uppercase token, got {self.prefix!r}")
        if not 1000 <= self.year <= 9999:
            raise ValueError(f"year must be a four-digit value, got {self.year!r}")
        if self.sequence < 1:
            raise ValueError(f"sequence must be positive, got {self.sequence!r}")

    @classmethod
    def create(cls, prefix: str, year: int, sequence: int) -> RegistrationNumber:
        """Build a registration number from its parts.

        Args:
            prefix: The uppercase deployment prefix.
            year: The four-digit calendar year.
            sequence: The positive per-year counter value.

        Returns:
            The validated registration number.
        """
        return cls(prefix=prefix, year=year, sequence=sequence)

    @classmethod
    def parse(cls, value: str) -> RegistrationNumber:
        """Parse a formatted registration number back into its parts.

        Args:
            value: A string of the form ``{PREFIX}-{YEAR}-{SEQUENCE}``.

        Returns:
            The parsed registration number.

        Raises:
            ValueError: If the string does not match the registration-number format.
        """
        match = _PATTERN.match(value)
        if match is None:
            raise ValueError(f"invalid registration number: {value!r}")
        return cls(
            prefix=match["prefix"],
            year=int(match["year"]),
            sequence=int(match["sequence"]),
        )

    def format(self) -> str:
        """Render the canonical string form.

        Returns:
            The registration number as ``{PREFIX}-{YEAR}-{SEQUENCE}`` with a zero-padded sequence.
        """
        return f"{self.prefix}-{self.year}-{self.sequence:0{_SEQUENCE_WIDTH}d}"

    def __str__(self) -> str:
        """Return the canonical string form.

        Returns:
            The value produced by :meth:`format`.
        """
        return self.format()

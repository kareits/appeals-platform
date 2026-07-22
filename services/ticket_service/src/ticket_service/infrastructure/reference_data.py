"""Validation of business dictionary codes.

Ticket fields such as channel, product, classifier, priority, decision, and closure reason store
dictionary codes. Use cases validate that a supplied code exists and is active before writing it, so
invalid classification or closure data cannot enter the regulatory register (CR-HIGH-006). Codes
that were valid when recorded remain readable after later deactivation — only new writes are
checked.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.application.errors import UnknownReferenceCodeError
from ticket_service.infrastructure.models import DictionaryEntry

DICT_CHANNEL = "channel"
DICT_PRODUCT = "product"
DICT_CLASSIFIER = "classifier"
DICT_PRIORITY = "priority"
DICT_DECISION = "decision"
DICT_CLOSURE_REASON = "closure_reason"


class ReferenceDataRepository:
    """Validates dictionary codes against the seeded, active reference data."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active database session.
        """
        self._session = session

    async def validate_active(self, pairs: Iterable[tuple[str, str]]) -> None:
        """Verify that every ``(dictionary_type, code)`` pair exists and is active.

        Args:
            pairs: The dictionary-type/code pairs to check.

        Raises:
            UnknownReferenceCodeError: If any pair is unknown or inactive.
        """
        wanted = list(dict.fromkeys(pairs))
        if not wanted:
            return
        conditions = [
            and_(DictionaryEntry.dictionary_type == dictionary_type, DictionaryEntry.code == code)
            for dictionary_type, code in wanted
        ]
        result = await self._session.execute(
            select(DictionaryEntry.dictionary_type, DictionaryEntry.code)
            .where(DictionaryEntry.is_active.is_(True))
            .where(or_(*conditions))
        )
        found = {(row.dictionary_type, row.code) for row in result}
        invalid = [pair for pair in wanted if pair not in found]
        if invalid:
            raise UnknownReferenceCodeError(invalid)

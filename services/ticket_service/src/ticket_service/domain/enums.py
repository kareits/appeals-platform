"""Enumerations for closed value sets owned by the ticket domain.

These enums cover value sets whose members are fixed by the domain itself (applicant kind,
identifier kind, data provenance). Open, business-configurable taxonomies (products, classifiers,
priorities, statuses, stages, decisions, closure reasons, regions) are stored as reference
dictionary rows instead (see :mod:`ticket_service.infrastructure.models`), because their members
are owned by the business (Q-A1) and evolve independently of code.
"""

from __future__ import annotations

from enum import StrEnum


class ApplicantType(StrEnum):
    """Role a party plays on a ticket.

    Attributes:
        CONSUMER: The consumer of financial services who submitted the appeal.
        REPRESENTATIVE: A party acting on the consumer's behalf.
    """

    CONSUMER = "CONSUMER"
    REPRESENTATIVE = "REPRESENTATIVE"


class IdentifierType(StrEnum):
    """Kind of national identifier held by a party.

    Attributes:
        IIN: Individual Identification Number (natural person).
        BIN: Business Identification Number (legal entity).
    """

    IIN = "IIN"
    BIN = "BIN"


class DataSource(StrEnum):
    """Provenance of a party's demographic data.

    Attributes:
        APPEAL: Extracted from the appeal itself.
        CORE_SYSTEM: Enriched from the core accounting system.
        MANUAL: Entered manually by an employee.
    """

    APPEAL = "APPEAL"
    CORE_SYSTEM = "CORE_SYSTEM"
    MANUAL = "MANUAL"

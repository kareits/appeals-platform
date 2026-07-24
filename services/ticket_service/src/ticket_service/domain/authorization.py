"""Data-scope and object-level authorization policy for the ticket service.

Permission claims decide *what kind* of action a caller may perform (checked at the route); this
module decides *which specific tickets* they may see or change, and separates **read** scope from
**mutation** scope so that combining roles cannot manufacture an unapproved composite capability
(CR-BFF-RR-HIGH-001). A controlled read/audit role never contributes mutation scope, even when the
caller also holds another role whose permission allows mutation.

It is a deliberately minimal, fail-closed EP-1 baseline (ADR-0008): the business
team/department/confidentiality matrix is not yet approved, so the policy grants the narrowest
defensible access and never widens by default. Department scope is not yet modeled; the team is the
scope unit for EP-1 (documented assumption), which is narrower than a department, hence fail-closed.

Roles are parsed from the token's ``roles`` claim into a local :class:`TicketRole` set; unknown role
names are ignored (they grant nothing). The policy is defined independently of the IAM role model
(ADR-004/ADR-007).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class TicketRole(StrEnum):
    """A platform role, as it appears in the token's ``roles`` claim.

    Defined independently of the IAM role enum (ADR-004); only the string values are shared.

    Attributes:
        EMPLOYEE: Second-line operator (team-scoped read and mutation).
        SUPERVISOR: Team lead with cross-team read and mutation.
        FIRST_LINE_READONLY: First-line read-only staff (team-scoped read; no mutation).
        OMBUDSMAN: Cross-team decision/closure authority (read and mutation).
        ANALYST: Cross-team read/analytics (read only; no mutation scope).
        ADMIN: Identity administrator; not a ticket operator.
        AUDITOR: Cross-team read-only across appeals and audit (no mutation scope).
    """

    EMPLOYEE = "EMPLOYEE"
    SUPERVISOR = "SUPERVISOR"
    FIRST_LINE_READONLY = "FIRST_LINE_READONLY"
    OMBUDSMAN = "OMBUDSMAN"
    ANALYST = "ANALYST"
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"


# Cross-team READ roles: oversight, analytics, and audit read any team's appeals.
_ORG_WIDE_READ: frozenset[TicketRole] = frozenset(
    {TicketRole.SUPERVISOR, TicketRole.OMBUDSMAN, TicketRole.ANALYST, TicketRole.AUDITOR}
)
# Cross-team MUTATION roles: only oversight/decision roles may change any team's appeals. Controlled
# read/audit roles (ANALYST, AUDITOR) are deliberately excluded so their scope cannot be borrowed by
# another role's mutation permission (CR-BFF-RR-HIGH-001).
_ORG_WIDE_WRITE: frozenset[TicketRole] = frozenset({TicketRole.SUPERVISOR, TicketRole.OMBUDSMAN})
# Team-scoped roles for READ: limited to their team, assignments, and registrations.
_TEAM_SCOPED_READ: frozenset[TicketRole] = frozenset(
    {TicketRole.EMPLOYEE, TicketRole.FIRST_LINE_READONLY}
)
# Team-scoped roles for MUTATION: only the operator role (first-line is read-only).
_TEAM_SCOPED_WRITE: frozenset[TicketRole] = frozenset({TicketRole.EMPLOYEE})
# Roles allowed to READ a confidential ticket. Fail-closed: everyone else is denied a confidential
# ticket even when they would otherwise have access (EP-1 assumption, ADR-0008).
_CONFIDENTIAL_READ: frozenset[TicketRole] = frozenset(
    {TicketRole.SUPERVISOR, TicketRole.OMBUDSMAN, TicketRole.AUDITOR}
)
# Roles allowed to MUTATE a confidential ticket. Narrower than read: the audit role may observe but
# never change a confidential ticket (least privilege; CR-BFF-RR-HIGH-001).
_CONFIDENTIAL_WRITE: frozenset[TicketRole] = frozenset(
    {TicketRole.SUPERVISOR, TicketRole.OMBUDSMAN}
)


@dataclass(frozen=True)
class TicketAccessContext:
    """The stored facts about a ticket needed to make an access decision.

    Attributes:
        team_id: The ticket's current team, if any.
        assignee_id: The ticket's current assignee, if any.
        registered_by: The subject who registered the ticket, if recorded.
        is_confidential: Whether the ticket is marked confidential.
    """

    team_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    registered_by: uuid.UUID | None
    is_confidential: bool


@dataclass(frozen=True)
class SearchScope:
    """The read scope applied to a search, derived from the caller's roles and teams.

    Attributes:
        all_access: When true, the caller may see tickets of any team (subject to confidentiality).
        team_ids: The caller's team identifiers, used when ``all_access`` is false.
        subject: The caller's subject, matched against assignee/registered_by.
        include_confidential: Whether the caller may see confidential tickets.
    """

    all_access: bool
    team_ids: frozenset[uuid.UUID]
    subject: uuid.UUID
    include_confidential: bool


def _roles_of(role_names: tuple[str, ...]) -> frozenset[TicketRole]:
    """Parse the token's role-name claim into known ticket roles, ignoring unknown names.

    Args:
        role_names: The raw role names from the token.

    Returns:
        The subset that are recognized ticket roles.
    """
    known: set[TicketRole] = set()
    for name in role_names:
        try:
            known.add(TicketRole(name))
        except ValueError:
            # An unknown role grants nothing; ignore it rather than fail the whole request.
            continue
    return frozenset(known)


def _team_ids_of(team_claims: tuple[str, ...]) -> frozenset[uuid.UUID]:
    """Parse the token's team claim into team identifiers, ignoring malformed values.

    Args:
        team_claims: The raw team identifiers from the token.

    Returns:
        The parsed team identifiers.
    """
    ids: set[uuid.UUID] = set()
    for value in team_claims:
        try:
            ids.add(uuid.UUID(value))
        except ValueError:
            continue
    return frozenset(ids)


def _team_match(
    subject: uuid.UUID, team_ids: frozenset[uuid.UUID], ticket: TicketAccessContext
) -> bool:
    """Return whether a team-scoped caller is connected to a ticket (team, assignee, or registrant).

    Args:
        subject: The caller's subject.
        team_ids: The caller's team identifiers.
        ticket: The target ticket facts.

    Returns:
        ``True`` when the caller is connected to the ticket.
    """
    if ticket.team_id is not None and ticket.team_id in team_ids:
        return True
    if ticket.assignee_id is not None and ticket.assignee_id == subject:
        return True
    return ticket.registered_by is not None and ticket.registered_by == subject


def _authorize(
    *,
    subject: uuid.UUID,
    roles: frozenset[TicketRole],
    team_claims: tuple[str, ...],
    ticket: TicketAccessContext,
    org_wide: frozenset[TicketRole],
    team_scoped: frozenset[TicketRole],
    confidential_allowed: frozenset[TicketRole],
) -> bool:
    """Evaluate access for one mode (read or mutation) using that mode's role sets.

    Args:
        subject: The caller's subject.
        roles: The caller's known roles.
        team_claims: The caller's team identifier claims.
        ticket: The target ticket facts.
        org_wide: The cross-team roles for this mode.
        team_scoped: The team-scoped roles for this mode.
        confidential_allowed: The roles allowed to act on a confidential ticket for this mode.

    Returns:
        ``True`` when access is permitted for this mode.
    """
    if not roles:
        return False
    # Confidentiality is an overriding restriction for this mode: without an allowed role, deny.
    if ticket.is_confidential and roles.isdisjoint(confidential_allowed):
        return False
    if not roles.isdisjoint(org_wide):
        return True
    if not roles.isdisjoint(team_scoped):
        return _team_match(subject, _team_ids_of(team_claims), ticket)
    return False


def can_read_ticket(
    *,
    subject: uuid.UUID,
    role_names: tuple[str, ...],
    team_claims: tuple[str, ...],
    ticket: TicketAccessContext,
) -> bool:
    """Decide whether a caller may read a specific ticket.

    Args:
        subject: The caller's subject.
        role_names: The caller's role-name claims.
        team_claims: The caller's team identifier claims.
        ticket: The stored facts about the target ticket.

    Returns:
        ``True`` when read access is permitted.
    """
    return _authorize(
        subject=subject,
        roles=_roles_of(role_names),
        team_claims=team_claims,
        ticket=ticket,
        org_wide=_ORG_WIDE_READ,
        team_scoped=_TEAM_SCOPED_READ,
        confidential_allowed=_CONFIDENTIAL_READ,
    )


def can_mutate_ticket(
    *,
    subject: uuid.UUID,
    role_names: tuple[str, ...],
    team_claims: tuple[str, ...],
    ticket: TicketAccessContext,
) -> bool:
    """Decide whether a caller may mutate a specific ticket.

    Mutation scope uses narrower role sets than read scope: controlled read/audit roles (ANALYST,
    AUDITOR) contribute no mutation scope, so their scope cannot be borrowed by another role's
    mutation permission (CR-BFF-RR-HIGH-001).

    Args:
        subject: The caller's subject.
        role_names: The caller's role-name claims.
        team_claims: The caller's team identifier claims.
        ticket: The stored facts about the target ticket.

    Returns:
        ``True`` when mutation access is permitted.
    """
    return _authorize(
        subject=subject,
        roles=_roles_of(role_names),
        team_claims=team_claims,
        ticket=ticket,
        org_wide=_ORG_WIDE_WRITE,
        team_scoped=_TEAM_SCOPED_WRITE,
        confidential_allowed=_CONFIDENTIAL_WRITE,
    )


def can_create_confidential(role_names: tuple[str, ...]) -> bool:
    """Decide whether a caller may register an appeal as confidential.

    A confidential appeal may only be created by a caller who can also *read* it, so creation,
    idempotent replay, and later reads have one consistent outcome (CR-BFF-R3-MEDIUM-001). Otherwise
    an operator could create an object the policy then immediately hides from them.

    Args:
        role_names: The caller's role-name claims.

    Returns:
        ``True`` when the caller holds a role cleared to read confidential appeals.
    """
    return not _roles_of(role_names).isdisjoint(_CONFIDENTIAL_READ)


def build_search_scope(
    *,
    subject: uuid.UUID,
    role_names: tuple[str, ...],
    team_claims: tuple[str, ...],
) -> SearchScope:
    """Derive the read scope applied to a search from the caller's roles and teams.

    Args:
        subject: The caller's subject.
        role_names: The caller's role-name claims.
        team_claims: The caller's team identifier claims.

    Returns:
        The scope constraining which tickets the search may return (read semantics).
    """
    roles = _roles_of(role_names)
    all_access = not roles.isdisjoint(_ORG_WIDE_READ)
    include_confidential = not roles.isdisjoint(_CONFIDENTIAL_READ)
    return SearchScope(
        all_access=all_access,
        team_ids=_team_ids_of(team_claims),
        subject=subject,
        include_confidential=include_confidential,
    )

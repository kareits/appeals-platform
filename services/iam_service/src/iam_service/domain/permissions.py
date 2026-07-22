"""Permissions and the role-to-permission authorization matrix.

This is the IAM service's authoritative authorization matrix. It lives inside the service that owns
roles (not in a shared library): ADR-007 forbids a shared permission-rule package, so each service
enforces access independently. IAM resolves a user's roles to a flat set of permission strings and
stamps them as claims on the issued token; downstream services check those claim strings.

Permissions use a ``resource:action`` convention. The matrix below is the EP-1 dev/local baseline
and is intentionally coarse; values may be refined in later phases without breaking the claim
format. The regulatory invariant enforced and tested here is that ``FIRST_LINE_READONLY`` carries a
read-only permission set (docs/01 first-line read-only; acceptance criteria).
"""

from __future__ import annotations

from enum import StrEnum

from iam_service.domain.roles import Role


class Permission(StrEnum):
    """A single ``resource:action`` permission claim.

    Attributes:
        TICKET_READ: View appeals (card, search, workspace).
        TICKET_CREATE: Register new appeals.
        TICKET_UPDATE: Edit mutable card details.
        TICKET_CLASSIFY: Set or change classification.
        TICKET_COMMENT: Add comments to an appeal.
        TICKET_ASSIGN: Assign or reassign an appeal to a team or employee.
        TICKET_DECIDE: Record a regulatory decision on an appeal.
        TICKET_CLOSE: Close an appeal.
        TICKET_LEGAL_HOLD: Place or lift a legal hold.
        REPORT_READ: Read reports and analytics.
        AUDIT_READ: Read the audit trail.
        IAM_MANAGE: Administer users, roles, and teams.
    """

    TICKET_READ = "ticket:read"
    TICKET_CREATE = "ticket:create"
    TICKET_UPDATE = "ticket:update"
    TICKET_CLASSIFY = "ticket:classify"
    TICKET_COMMENT = "ticket:comment"
    TICKET_ASSIGN = "ticket:assign"
    TICKET_DECIDE = "ticket:decide"
    TICKET_CLOSE = "ticket:close"
    TICKET_LEGAL_HOLD = "ticket:legal_hold"
    REPORT_READ = "report:read"
    AUDIT_READ = "audit:read"
    IAM_MANAGE = "iam:manage"


# Read-only permission set shared by the read-only roles. Kept as a named constant so the
# first-line read-only invariant is expressed once and asserted directly in tests.
_TICKET_READONLY: frozenset[Permission] = frozenset({Permission.TICKET_READ})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.EMPLOYEE: frozenset(
        {
            Permission.TICKET_READ,
            Permission.TICKET_CREATE,
            Permission.TICKET_UPDATE,
            Permission.TICKET_CLASSIFY,
            Permission.TICKET_COMMENT,
        }
    ),
    Role.SUPERVISOR: frozenset(
        {
            Permission.TICKET_READ,
            Permission.TICKET_CREATE,
            Permission.TICKET_UPDATE,
            Permission.TICKET_CLASSIFY,
            Permission.TICKET_COMMENT,
            Permission.TICKET_ASSIGN,
            Permission.TICKET_DECIDE,
            Permission.TICKET_CLOSE,
            Permission.TICKET_LEGAL_HOLD,
        }
    ),
    # Regulatory: first-line staff observe but never mutate appeals (docs/01).
    Role.FIRST_LINE_READONLY: _TICKET_READONLY,
    Role.OMBUDSMAN: frozenset(
        {
            Permission.TICKET_READ,
            Permission.TICKET_COMMENT,
            Permission.TICKET_DECIDE,
            Permission.TICKET_CLOSE,
            Permission.TICKET_LEGAL_HOLD,
        }
    ),
    Role.ANALYST: frozenset({Permission.TICKET_READ, Permission.REPORT_READ}),
    # Auditors have read-only visibility across appeals, reports, and the audit trail (docs/06).
    Role.AUDITOR: frozenset(
        {Permission.TICKET_READ, Permission.REPORT_READ, Permission.AUDIT_READ}
    ),
    # Administrators manage identity only; they are not ticket operators.
    Role.ADMIN: frozenset({Permission.IAM_MANAGE}),
}
"""Authoritative mapping from each role to the permissions it grants (EP-1 dev/local baseline)."""

# Permissions that never mutate protected state; used to assert the read-only invariant in tests.
READ_ONLY_PERMISSIONS: frozenset[Permission] = frozenset(
    {Permission.TICKET_READ, Permission.REPORT_READ, Permission.AUDIT_READ}
)


def resolve_permissions(roles: frozenset[Role] | set[Role] | list[Role]) -> frozenset[Permission]:
    """Resolve a set of roles to the union of their permissions.

    Args:
        roles: The roles held by a subject.

    Returns:
        The union of permissions granted by the given roles (empty when no role grants any).
    """
    resolved: set[Permission] = set()
    for role in roles:
        resolved |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(resolved)

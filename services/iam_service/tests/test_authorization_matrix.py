"""Unit tests for the role-to-permission authorization matrix.

These assert the regulatory invariant that first-line staff are read-only (docs/01) and that the
matrix covers all seven roles, so the acceptance criterion "first-line read-only enforced at the
permission level" is checked directly against the source of authorization truth.
"""

from __future__ import annotations

from iam_service.domain.permissions import (
    READ_ONLY_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
    resolve_permissions,
)
from iam_service.domain.roles import Role


def test_matrix_covers_all_roles() -> None:
    """Every role has an entry in the authorization matrix."""
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_first_line_is_read_only() -> None:
    """FIRST_LINE_READONLY grants only ticket read and no mutating permission."""
    permissions = ROLE_PERMISSIONS[Role.FIRST_LINE_READONLY]
    assert permissions == frozenset({Permission.TICKET_READ})
    assert permissions <= READ_ONLY_PERMISSIONS


def test_auditor_is_read_only() -> None:
    """AUDITOR holds only read-only permissions across appeals, reports, and audit."""
    assert ROLE_PERMISSIONS[Role.AUDITOR] <= READ_ONLY_PERMISSIONS


def test_only_supervisor_and_ombudsman_may_decide_and_close() -> None:
    """Recording decisions and closing appeals is limited to SUPERVISOR and OMBUDSMAN."""
    deciders = {
        role
        for role, perms in ROLE_PERMISSIONS.items()
        if Permission.TICKET_DECIDE in perms or Permission.TICKET_CLOSE in perms
    }
    assert deciders == {Role.SUPERVISOR, Role.OMBUDSMAN}


def test_admin_manages_identity_only() -> None:
    """ADMIN holds identity management and is not a ticket operator."""
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset({Permission.IAM_MANAGE})


def test_resolve_permissions_unions_roles() -> None:
    """Resolving multiple roles returns the union of their permissions."""
    resolved = resolve_permissions({Role.ANALYST, Role.FIRST_LINE_READONLY})
    assert Permission.TICKET_READ in resolved
    assert Permission.REPORT_READ in resolved
    assert Permission.TICKET_UPDATE not in resolved


def test_resolve_permissions_empty_for_no_roles() -> None:
    """A subject with no roles has no permissions."""
    assert resolve_permissions(set()) == frozenset()

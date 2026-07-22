"""Platform roles owned by the IAM domain.

The seven roles are a closed value set fixed by the domain (IAM_SERVICE spec): they are stable
identifiers assigned to users, not a business-configurable taxonomy. Each role maps to a set of
permissions in :mod:`iam_service.domain.permissions`; downstream services authorize on the resolved
permissions rather than on role names, so role membership can evolve without changing callers.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """A platform role assignable to a user (IAM_SERVICE spec).

    Attributes:
        EMPLOYEE: Second-line operator who registers and works appeals.
        SUPERVISOR: Team lead who assigns work and records decisions/closure.
        FIRST_LINE_READONLY: First-line staff with read-only visibility (no mutations).
        OMBUDSMAN: Authorized to record decisions and close appeals.
        ANALYST: Reads appeals and analytics/reports.
        ADMIN: Administers identity (users, roles, teams); not a ticket operator.
        AUDITOR: Read-only access across appeals, reports, and the audit trail.
    """

    EMPLOYEE = "EMPLOYEE"
    SUPERVISOR = "SUPERVISOR"
    FIRST_LINE_READONLY = "FIRST_LINE_READONLY"
    OMBUDSMAN = "OMBUDSMAN"
    ANALYST = "ANALYST"
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"

"""The appeal-scope port: the trusted decision on whether a caller may reach an appeal.

Documents are evidence attached to appeals, so "may this caller see this document?" is really "may
this caller see this appeal?" — and "may this caller attach or move this evidence?" is "may this
caller *modify* that appeal's record?". Both answers depend on team, assignment, and
confidentiality, which are data the **Ticket Service** owns. This service must not read that
database (root ``CLAUDE.md``, ADR-004), and reimplementing the rules here would duplicate a policy
that ADR-0008 already makes authoritative elsewhere, guaranteeing drift.

The decisions are therefore delegated through this port, and **read and write are separate
questions**. Ticket's mutation scope is deliberately narrower than its read scope: the controlled
read/audit roles (ANALYST, AUDITOR) grant organization-wide read but no mutation scope, and AUDITOR
may read a confidential appeal without being able to change it. Treating a successful read as
permission to write would let one role's breadth combine with another role's ``ticket:update``
permission — the composite escalation Ticket prevents (CR-DOC-HIGH-002, CR-BFF-RR-HIGH-001).

Every failure mode is closed: an explicit denial, an unreachable decision point, and an unexpected
answer all end in "no access", never in an assumed yes.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


class AppealScopeDeniedError(Exception):
    """Raised when the caller may not perform the attempted operation on the appeal (403).

    Carries no detail about the appeal: a caller outside its scope must not learn whether it exists.
    """


class AppealScopeUnavailableError(Exception):
    """Raised when no trusted scope decision could be obtained (mapped to 503).

    Deliberately distinct from a denial: the request is refused because the authorization decision
    is unavailable, not because it was negative. Failing closed here is what keeps an outage of the
    decision point from turning into open access to stored evidence.
    """


@runtime_checkable
class AppealScopeChecker(Protocol):
    """Decides whether an authenticated caller may read, or modify, a given appeal."""

    async def ensure_appeal_read_access(self, ticket_id: uuid.UUID, access_token: str) -> None:
        """Authorize reading an appeal's evidence, raising when access is not established.

        Args:
            ticket_id: The appeal the caller is trying to read.
            access_token: The caller's own bearer token, forwarded so the decision is made for the
                caller rather than for a privileged service identity.

        Raises:
            AppealScopeDeniedError: The caller may not read the appeal (including the case where it
                does not exist, which is indistinguishable from the caller's point of view).
            AppealScopeUnavailableError: No trusted decision could be obtained.
        """
        ...

    async def ensure_appeal_write_access(self, ticket_id: uuid.UUID, access_token: str) -> None:
        """Authorize modifying an appeal's evidence, raising when access is not established.

        Implementations must obtain a genuine *mutation* decision. Inferring one from a successful
        read is the defect this separation exists to prevent (CR-DOC-HIGH-002).

        Args:
            ticket_id: The appeal whose evidence the caller is trying to change.
            access_token: The caller's own bearer token.

        Raises:
            AppealScopeDeniedError: The caller may not modify the appeal.
            AppealScopeUnavailableError: No trusted decision could be obtained.
        """
        ...

"""Permission claim strings enforced by the document service.

The service authorizes on permission *claim strings* (``resource:action``), not on role names, and
defines these values independently of the IAM service (ADR-004 forbids importing IAM code; ADR-007
forbids a shared permission package). IAM resolves a user's roles to permissions and stamps them as
token claims; the document service checks the claim strings here. The values must stay in sync with
the strings IAM issues.

**Why appeal permissions and not ``document:*``.** Documents exist only as evidence attached to an
appeal, and the IAM matrix in force (TASK_01D) grants no ``document:*`` permission to any role, so
enforcing one would deny every real caller. Reading document metadata or content therefore requires
``ticket:read`` and attaching or linking a document requires ``ticket:update`` — a caller who may
edit an appeal may add evidence to it. Dedicated ``document:*`` permissions are a deliberate follow-
up together with the IAM matrix revision (see the service README "Known limitations").

**Scope, not object-level authorization.** These checks are permission-level only. Whether the
caller may see *this particular* appeal (team scope, confidentiality) is decided from data the
Ticket Service owns, which this service must not read (root ``CLAUDE.md``). Object-level document
scope is therefore an open item recorded in the README and carried with the business RBAC matrix.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentPermission(StrEnum):
    """A permission claim string checked on every document route.

    Attributes:
        READ: View document metadata, list an appeal's documents, and download content.
        WRITE: Upload a document and link it to an appeal.
    """

    READ = "ticket:read"
    WRITE = "ticket:update"

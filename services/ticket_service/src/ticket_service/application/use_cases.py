"""Ticket use cases (application services).

Each use case coordinates repositories, the registration-number allocator, domain invariants, and
the transactional outbox within the caller's unit of work. Business logic lives here rather than in
API route handlers (root ``CLAUDE.md``). Use cases stage events but never commit; the API's
unit-of-work dependency owns the transaction boundary.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, tzinfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ticket_service.application import events
from ticket_service.application.commands import (
    AddCommentCommand,
    ApplicantInput,
    ClassifyTicketCommand,
    CloseTicketCommand,
    CreateTicketCommand,
    RecordDecisionCommand,
    SetLegalHoldCommand,
    TicketSearchQuery,
    UpdateTicketCommand,
)
from ticket_service.application.errors import (
    AuthorizationError,
    IdempotencyConflictError,
    LegacyIdempotencyError,
    TicketNotFoundError,
    VersionConflictError,
)
from ticket_service.domain import authorization
from ticket_service.domain.authorization import SearchScope, TicketAccessContext
from ticket_service.domain.invariants import (
    ClosureState,
    check_can_close,
    check_registration_fields,
    resolve_retention_until,
)
from ticket_service.domain.sla import DEFAULT_SLA_POLICY, compute_due_dates
from ticket_service.infrastructure import audit, reference_data
from ticket_service.infrastructure.audit import AuditRepository
from ticket_service.infrastructure.auth_tokens import TicketClaims
from ticket_service.infrastructure.models import (
    DictionaryEntry,
    Ticket,
    TicketApplicant,
    TicketComment,
)
from ticket_service.infrastructure.outbox import OutboxRepository
from ticket_service.infrastructure.reference_data import ReferenceDataRepository
from ticket_service.infrastructure.registration import RegistrationNumberAllocator
from ticket_service.infrastructure.repositories import CommentRepository, TicketRepository

# Initial projection codes for a freshly registered appeal. Status and stage advance only through
# the Flowable projection later (EP-3); in EP-1 they hold these placeholders (IMPLEMENTATION_PLAN).
DEFAULT_STATUS_CODE = "NEW"
DEFAULT_STAGE_CODE = "REGISTRATION"

# Terminal codes set by the close use case. In EP-1 the ticket service performs the close directly
# (a placeholder projection); Flowable drives interim statuses later (IMPLEMENTATION_PLAN).
CLOSED_STATUS_CODE = "COMPLETED"
CLOSED_STAGE_CODE = "CLOSED"

# Card fields an update may change. Status, stage, and assignment are deliberately excluded.
_UPDATABLE_FIELDS = ("subject", "description", "source_channel_code", "contract_number")


def _access_context(ticket: Ticket) -> TicketAccessContext:
    """Extract the authorization-relevant facts from a ticket.

    Args:
        ticket: The stored ticket.

    Returns:
        The context used by the data-scope policy.
    """
    return TicketAccessContext(
        team_id=ticket.current_team_id,
        assignee_id=ticket.current_assignee_id,
        registered_by=ticket.registered_by,
        is_confidential=ticket.is_confidential,
    )


def _ensure_read(caller: TicketClaims, ticket: Ticket) -> None:
    """Enforce read-scope for a caller against a specific ticket.

    Args:
        caller: The authenticated caller's claims.
        ticket: The target ticket.

    Raises:
        AuthorizationError: If the caller may not read this ticket.
    """
    if not authorization.can_read_ticket(
        subject=caller.subject,
        role_names=caller.roles,
        team_claims=caller.teams,
        ticket=_access_context(ticket),
    ):
        raise AuthorizationError("the caller is not permitted to read this ticket")


def _ensure_mutate(caller: TicketClaims, ticket: Ticket) -> None:
    """Enforce mutation-scope for a caller against a specific ticket.

    Mutation scope is narrower than read scope, so a controlled read/audit role cannot lend its
    scope to another role's mutation permission (CR-BFF-RR-HIGH-001).

    Args:
        caller: The authenticated caller's claims.
        ticket: The target ticket.

    Raises:
        AuthorizationError: If the caller may not mutate this ticket.
    """
    if not authorization.can_mutate_ticket(
        subject=caller.subject,
        role_names=caller.roles,
        team_claims=caller.teams,
        ticket=_access_context(ticket),
    ):
        raise AuthorizationError("the caller is not permitted to modify this ticket")


def _scoped_idempotency_key(subject: uuid.UUID, raw_key: str) -> str:
    """Namespace a client idempotency key to the authenticated subject.

    Idempotency keys are a per-caller namespace, not a global object lookup: prefixing with the
    subject means one caller's key can never collide with, replay, or disclose another caller's
    appeal (CR-BFF-RR-BLOCKER-001). The stored value is unique cluster-wide (existing column
    constraint) while remaining private to the subject.

    Args:
        subject: The authenticated caller's subject.
        raw_key: The client-supplied idempotency key.

    Returns:
        A fixed-width SHA-256 digest of the subject-namespaced key (fits the storage column).
    """
    return hashlib.sha256(f"{subject}:{raw_key}".encode()).hexdigest()


def _request_fingerprint(command: CreateTicketCommand) -> str:
    """Compute a canonical fingerprint of a registration request (excluding the idempotency key).

    Lets a same-caller replay with the same key but a *different* payload be rejected as a conflict
    rather than silently returning the original ticket (CR-BFF-RR-BLOCKER-001).

    Args:
        command: The registration command.

    Returns:
        A hex SHA-256 fingerprint of the canonicalized request.
    """
    payload = dataclasses.asdict(command)
    payload.pop("idempotency_key", None)
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotent_hit(
    existing: Ticket, caller: TicketClaims, fingerprint: str
) -> tuple[Ticket, bool]:
    """Return the existing ticket for a valid replay, or raise on a payload/caller mismatch.

    Args:
        existing: The ticket previously stored under the scoped key.
        caller: The authenticated caller.
        fingerprint: The current request fingerprint.

    Returns:
        The existing ticket and ``False`` (not newly created) for a matching replay.

    Raises:
        AuthorizationError: If the caller may not read the existing ticket (defence in depth).
        IdempotencyConflictError: If the stored fingerprint differs from the current request.
    """
    # Defence in depth: the scoped key already guarantees the same subject, but re-check read scope.
    _ensure_read(caller, existing)
    if existing.idempotency_fingerprint != fingerprint:
        raise IdempotencyConflictError(
            "the idempotency key was reused with a different request payload"
        )
    return existing, False


def _to_applicant(source: ApplicantInput) -> TicketApplicant:
    """Map an applicant input to a persistent applicant row.

    Args:
        source: The applicant input.

    Returns:
        The corresponding ORM applicant (not yet associated with a ticket).
    """
    return TicketApplicant(
        applicant_type=source.applicant_type,
        data_source=source.data_source,
        full_name=source.full_name,
        identifier_type=source.identifier_type,
        identifier_value=source.identifier_value,
        email=source.email,
        phone=source.phone,
        gender_code=source.gender_code,
        birth_date=source.birth_date,
        age=source.age,
        region_code=source.region_code,
        representative_basis=source.representative_basis,
    )


async def create_manual_ticket(
    session: AsyncSession,
    allocator: RegistrationNumberAllocator,
    command: CreateTicketCommand,
    caller: TicketClaims,
) -> tuple[Ticket, bool]:
    """Register an appeal manually and stage ``ticket.created.v1``.

    When an idempotency key is supplied and a ticket already exists for it, the existing ticket is
    returned unchanged (no duplicate, no second event). The registrant (``registered_by``) and the
    audit actor are the verified caller, never client input (CR-BFF-BLOCKER-001).

    Args:
        session: The active unit-of-work session.
        allocator: Allocator issuing the unique registration number.
        command: The registration input.
        caller: The authenticated caller (the registering subject).

    Returns:
        A tuple of the ticket and whether it was newly created (``False`` on an idempotent hit).

    Raises:
        TicketInvariantError: If a required registration field is missing.
    """
    tickets = TicketRepository(session)
    outbox = OutboxRepository(session)

    # Confidentiality is set only by a caller who can also read the result, so create, idempotent
    # replay, and later reads have one consistent outcome (CR-BFF-R3-MEDIUM-001).
    if command.is_confidential and not authorization.can_create_confidential(caller.roles):
        raise AuthorizationError(
            "only a confidentiality-cleared role may register a confidential appeal"
        )

    scoped_key: str | None = None
    fingerprint = _request_fingerprint(command)
    if command.idempotency_key is not None:
        scoped_key = _scoped_idempotency_key(caller.subject, command.idempotency_key)
        existing = await tickets.get_by_idempotency_key(scoped_key)
        if existing is not None:
            return _idempotent_hit(existing, caller, fingerprint)
        # A pre-upgrade row stored the raw key with no fingerprint; a retry of such a legacy
        # registration is refused (non-disclosing 409) rather than duplicated (CR-BFF-R3-HIGH-001).
        legacy = await tickets.get_by_idempotency_key(command.idempotency_key)
        if legacy is not None and legacy.idempotency_fingerprint is None:
            raise LegacyIdempotencyError(str(command.idempotency_key))

    await ReferenceDataRepository(session).validate_active(
        [
            (reference_data.DICT_CHANNEL, command.source_channel_code),
            (reference_data.DICT_PRODUCT, command.product_code),
            (reference_data.DICT_CLASSIFIER, command.classifier_code),
            (reference_data.DICT_PRIORITY, command.priority_code),
        ]
    )

    now = datetime.now(UTC)
    # Ticket Service owns SLA deadlines; compute them from the received time (ADR-009/ADR-0005).
    due = compute_due_dates(command.received_at)
    consumer = _to_applicant(command.applicant)

    try:
        # Allocate the number and insert the ticket atomically in a savepoint so a concurrent
        # duplicate idempotency key rolls back the reserved number instead of leaving a partial
        # write and returns the original result (CR-HIGH-005).
        async with session.begin_nested():
            number = await allocator.allocate(session, at=now)
            ticket = Ticket(
                registration_number=number.format(),
                idempotency_key=scoped_key,
                idempotency_fingerprint=fingerprint,
                received_at=command.received_at,
                registered_at=now,
                source_channel_code=command.source_channel_code,
                subject=command.subject,
                description=command.description,
                contract_number=command.contract_number,
                product_code=command.product_code,
                classifier_code=command.classifier_code,
                priority_code=command.priority_code,
                current_status_code=DEFAULT_STATUS_CODE,
                current_stage_code=DEFAULT_STAGE_CODE,
                internal_due_at=due.internal_due_at,
                legal_due_at=due.legal_due_at,
                sla_policy_version=DEFAULT_SLA_POLICY.version,
                # Server-derived ownership: the registering subject owns the ticket for data-scope
                # until Flowable assigns a team/assignee (EP-1, ADR-0008). Never client-supplied.
                registered_by=caller.subject,
                is_confidential=command.is_confidential,
            )
            check_registration_fields(
                {
                    "registration_number": ticket.registration_number,
                    "received_at": ticket.received_at,
                    "registered_at": ticket.registered_at,
                    "source_channel_code": ticket.source_channel_code,
                    "subject": ticket.subject,
                    "description": ticket.description,
                    "product_code": ticket.product_code,
                    "classifier_code": ticket.classifier_code,
                    "priority_code": ticket.priority_code,
                    "current_status_code": ticket.current_status_code,
                    "current_stage_code": ticket.current_stage_code,
                }
            )
            ticket.applicants.append(consumer)
            if command.representative is not None:
                ticket.applicants.append(_to_applicant(command.representative))
            tickets.add(ticket)
            await session.flush()

            await outbox.enqueue(
                events.ticket_created_event(ticket, consumer, command.representative is not None)
            )
            AuditRepository(session).record(
                entity_id=ticket.id,
                action=audit.ACTION_REGISTERED,
                actor_id=caller.subject,
                details={"registrationNumber": ticket.registration_number},
            )
            return ticket, True
    except IntegrityError:
        # A concurrent request with the same scoped idempotency key won the insert; return the
        # original only after the same caller/payload check as the fast path (never disclose another
        # caller's appeal, and reject a mismatched payload) (CR-BFF-RR-BLOCKER-001).
        if scoped_key is not None:
            existing = await tickets.get_by_idempotency_key(scoped_key)
            if existing is not None:
                return _idempotent_hit(existing, caller, fingerprint)
        raise


async def update_ticket_details(
    session: AsyncSession, command: UpdateTicketCommand, caller: TicketClaims
) -> Ticket:
    """Update editable appeal-card fields and stage ``ticket.updated.v1``.

    Args:
        session: The active unit-of-work session.
        command: The update input (only provided fields are applied).
        caller: The authenticated caller (enforced against the ticket's data scope).

    Returns:
        The updated ticket.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)
    _ensure_mutate(caller, ticket)

    if "source_channel_code" in command.provided and command.source_channel_code is not None:
        await ReferenceDataRepository(session).validate_active(
            [(reference_data.DICT_CHANNEL, command.source_channel_code)]
        )

    changed: list[str] = []
    for name in _UPDATABLE_FIELDS:
        if name not in command.provided:
            continue
        new_value = getattr(command, name)
        if getattr(ticket, name) != new_value:
            setattr(ticket, name, new_value)
            changed.append(name)

    if not changed:
        return ticket

    await session.flush()
    await OutboxRepository(session).enqueue(events.ticket_updated_event(ticket.id, changed))
    AuditRepository(session).record(
        entity_id=ticket.id,
        action=audit.ACTION_UPDATED,
        actor_id=caller.subject,
        details={"changedFields": changed},
    )
    return ticket


async def classify_ticket(
    session: AsyncSession, command: ClassifyTicketCommand, caller: TicketClaims
) -> Ticket:
    """Set an appeal's classification and stage ``ticket.classified.v1``.

    Args:
        session: The active unit-of-work session.
        command: The classification input.
        caller: The authenticated caller (enforced against the ticket's data scope).

    Returns:
        The reclassified ticket.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)
    _ensure_mutate(caller, ticket)
    await ReferenceDataRepository(session).validate_active(
        [
            (reference_data.DICT_PRODUCT, command.product_code),
            (reference_data.DICT_CLASSIFIER, command.classifier_code),
            (reference_data.DICT_PRIORITY, command.priority_code),
        ]
    )
    ticket.product_code = command.product_code
    ticket.classifier_code = command.classifier_code
    ticket.priority_code = command.priority_code
    await session.flush()
    await OutboxRepository(session).enqueue(events.ticket_classified_event(ticket))
    AuditRepository(session).record(
        entity_id=ticket.id,
        action=audit.ACTION_CLASSIFIED,
        actor_id=caller.subject,
        details={"classifierCode": ticket.classifier_code, "productCode": ticket.product_code},
    )
    return ticket


async def record_decision(
    session: AsyncSession, command: RecordDecisionCommand, caller: TicketClaims
) -> Ticket:
    """Record the decision on an appeal and stage ``ticket.decision_recorded.v1``.

    The deciding employee (``decision_by``) and the audit actor are the verified caller, never
    client input (CR-BFF-BLOCKER-001).

    Args:
        session: The active unit-of-work session.
        command: The decision input.
        caller: The authenticated caller (the deciding subject).

    Returns:
        The ticket with the decision recorded.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)
    _ensure_mutate(caller, ticket)
    await ReferenceDataRepository(session).validate_active(
        [(reference_data.DICT_DECISION, command.decision_code)]
    )
    ticket.decision_code = command.decision_code
    ticket.decision_summary = command.decision_summary
    ticket.decision_text = command.decision_text
    ticket.decision_by = caller.subject
    ticket.decision_at = datetime.now(UTC)
    await session.flush()
    await OutboxRepository(session).enqueue(events.ticket_decision_recorded_event(ticket))
    AuditRepository(session).record(
        entity_id=ticket.id,
        action=audit.ACTION_DECISION_RECORDED,
        actor_id=caller.subject,
        details={"decisionCode": ticket.decision_code},
    )
    return ticket


async def close_ticket(
    session: AsyncSession,
    command: CloseTicketCommand,
    caller: TicketClaims,
    tz: tzinfo | None = None,
) -> Ticket:
    """Close an appeal after validating the regulatory prerequisites.

    Verifies that a decision, decision text, responsible employee, decision date, a response date
    or a justified absence of response, and a closure reason are present (docs/01), then sets the
    closure fields, the retention date (at least five years, computed in the business timezone), and
    the terminal status. Stages ``ticket.closed.v1``. The audit actor is the verified caller.

    Args:
        session: The active unit-of-work session.
        command: The closure input.
        caller: The authenticated caller (the closing subject).
        tz: The business timezone for the retention date; defaults to Asia/Almaty.

    Returns:
        The closed ticket.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
        TicketInvariantError: If a closure prerequisite is unmet.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)
    _ensure_mutate(caller, ticket)
    await ReferenceDataRepository(session).validate_active(
        [(reference_data.DICT_CLOSURE_REASON, command.closure_reason_code)]
    )
    check_can_close(
        ClosureState(
            decision_code=ticket.decision_code,
            decision_text=ticket.decision_text,
            decision_at=ticket.decision_at,
            decision_by=ticket.decision_by,
            response_sent_at=command.response_sent_at,
            no_response_reason=command.no_response_reason,
            closure_reason_code=command.closure_reason_code,
        )
    )

    closed_at = datetime.now(UTC)
    ticket.closure_reason_code = command.closure_reason_code
    ticket.response_sent_at = command.response_sent_at
    ticket.no_response_reason = command.no_response_reason
    ticket.closed_at = closed_at
    ticket.retention_until = resolve_retention_until(closed_at, tz)
    ticket.current_status_code = CLOSED_STATUS_CODE
    ticket.current_stage_code = CLOSED_STAGE_CODE
    await session.flush()
    await OutboxRepository(session).enqueue(events.ticket_closed_event(ticket))
    AuditRepository(session).record(
        entity_id=ticket.id,
        action=audit.ACTION_CLOSED,
        actor_id=caller.subject,
        details={
            "closureReasonCode": ticket.closure_reason_code,
            "retentionUntil": ticket.retention_until.isoformat()
            if ticket.retention_until
            else None,
        },
    )
    return ticket


async def set_legal_hold(
    session: AsyncSession, command: SetLegalHoldCommand, caller: TicketClaims
) -> Ticket:
    """Place or lift a legal hold on an appeal and audit the change.

    Args:
        session: The active unit-of-work session.
        command: The legal-hold input.
        caller: The authenticated caller (the acting subject).

    Returns:
        The updated ticket.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If ``expected_version`` does not match the stored version.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await _load_for_write(session, command.ticket_id, command.expected_version)
    _ensure_mutate(caller, ticket)
    ticket.legal_hold = command.legal_hold
    await session.flush()
    AuditRepository(session).record(
        entity_id=ticket.id,
        action=audit.ACTION_LEGAL_HOLD_SET,
        actor_id=caller.subject,
        details={"legalHold": command.legal_hold, "reason": command.reason},
    )
    return ticket


async def get_ticket(session: AsyncSession, ticket_id: uuid.UUID, caller: TicketClaims) -> Ticket:
    """Load an appeal card by identifier, enforcing the caller's data scope.

    Args:
        session: The active session.
        ticket_id: The ticket identifier.
        caller: The authenticated caller (enforced against the ticket's data scope).

    Returns:
        The ticket with its applicants.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise TicketNotFoundError(str(ticket_id))
    _ensure_read(caller, ticket)
    return ticket


async def add_comment(
    session: AsyncSession, command: AddCommentCommand, caller: TicketClaims
) -> TicketComment:
    """Add a comment to an appeal.

    The comment author and the audit actor are the verified caller, never client input
    (CR-BFF-BLOCKER-001).

    Args:
        session: The active unit-of-work session.
        command: The comment input.
        caller: The authenticated caller (the comment author).

    Returns:
        The created comment.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await TicketRepository(session).get(command.ticket_id)
    if ticket is None:
        raise TicketNotFoundError(str(command.ticket_id))
    _ensure_mutate(caller, ticket)

    comment = TicketComment(
        ticket_id=command.ticket_id, author_id=caller.subject, body=command.body
    )
    CommentRepository(session).add(comment)
    await session.flush()
    AuditRepository(session).record(
        entity_id=command.ticket_id,
        action=audit.ACTION_COMMENT_ADDED,
        actor_id=caller.subject,
        details={"commentId": str(comment.id)},
    )
    return comment


async def list_comments(
    session: AsyncSession, ticket_id: uuid.UUID, caller: TicketClaims
) -> Sequence[TicketComment]:
    """List an appeal's comments, verifying the appeal exists and the caller may access it.

    Args:
        session: The active session.
        ticket_id: The owning ticket identifier.
        caller: The authenticated caller (enforced against the ticket's data scope).

    Returns:
        The comments ordered newest first.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        AuthorizationError: If the caller may not access this ticket.
    """
    ticket = await TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise TicketNotFoundError(str(ticket_id))
    _ensure_read(caller, ticket)
    return await CommentRepository(session).list_for_ticket(ticket_id)


async def search_tickets(
    session: AsyncSession, query: TicketSearchQuery, scope: SearchScope
) -> tuple[Sequence[Ticket], int]:
    """Search appeals by the supported filters, constrained to the caller's read scope.

    Args:
        session: The active session.
        query: The search filters and pagination.
        scope: The caller's read scope (team/ownership/confidentiality), applied as extra filters so
            a team-scoped caller cannot enumerate other teams' tickets.

    Returns:
        A tuple of the page's tickets and the total match count.
    """
    return await TicketRepository(session).search(query, scope)


async def list_reference_data(
    session: AsyncSession, types: Sequence[str] | None = None
) -> Sequence[DictionaryEntry]:
    """List active reference-dictionary entries used to populate registration/classification forms.

    Args:
        session: The active session.
        types: Optional dictionary types to include; when ``None`` or empty, all types are returned.

    Returns:
        The active entries in a deterministic presentation order (type, sort order, code).
    """
    return await ReferenceDataRepository(session).list_active(types)


async def _load_for_write(
    session: AsyncSession, ticket_id: uuid.UUID, expected_version: int
) -> Ticket:
    """Load a ticket for modification, enforcing existence and optimistic locking.

    Args:
        session: The active session.
        ticket_id: The ticket identifier.
        expected_version: The version the client last observed.

    Returns:
        The ticket ready for modification.

    Raises:
        TicketNotFoundError: If the ticket does not exist.
        VersionConflictError: If the stored version differs from ``expected_version``.
    """
    ticket = await TicketRepository(session).get(ticket_id)
    if ticket is None:
        raise TicketNotFoundError(str(ticket_id))
    if ticket.version != expected_version:
        raise VersionConflictError(expected_version, ticket.version)
    return ticket

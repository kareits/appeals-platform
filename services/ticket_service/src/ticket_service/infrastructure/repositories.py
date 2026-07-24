"""Persistence repositories for tickets and comments.

Repositories encapsulate query construction (including the TASK_01B search) so use cases stay free
of SQL. They operate on the caller's session and never commit; the surrounding unit of work owns
the transaction boundary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ticket_service.application.commands import TicketSearchQuery
from ticket_service.domain.authorization import SearchScope
from ticket_service.infrastructure.models import Ticket, TicketApplicant, TicketComment


class TicketRepository:
    """Reads and writes tickets."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active database session.
        """
        self._session = session

    def add(self, ticket: Ticket) -> None:
        """Stage a new ticket for insertion.

        Args:
            ticket: The ticket to add.
        """
        self._session.add(ticket)

    async def get(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Load a ticket with its applicants.

        Args:
            ticket_id: The ticket identifier.

        Returns:
            The ticket, or ``None`` if it does not exist.
        """
        result = await self._session.execute(
            select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.applicants))
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> Ticket | None:
        """Load a ticket previously created with a given idempotency key.

        Args:
            key: The idempotency key.

        Returns:
            The matching ticket with its applicants, or ``None``.
        """
        result = await self._session.execute(
            select(Ticket)
            .where(Ticket.idempotency_key == key)
            .options(selectinload(Ticket.applicants))
        )
        return result.scalar_one_or_none()

    async def search(
        self, query: TicketSearchQuery, scope: SearchScope
    ) -> tuple[Sequence[Ticket], int]:
        """Search tickets by the supported filters, constrained to the caller's read scope.

        Args:
            query: The search filters and pagination.
            scope: The caller's read scope (team/ownership/confidentiality), ANDed with the filters.

        Returns:
            A tuple of the page's tickets (newest registration first) and the total match count.
        """
        conditions = self._build_conditions(query) + self._scope_conditions(scope)

        total = await self._session.scalar(
            select(func.count()).select_from(Ticket).where(*conditions)
        )

        offset = (query.page - 1) * query.page_size
        page_stmt: Select[tuple[Ticket]] = (
            select(Ticket)
            .where(*conditions)
            .order_by(Ticket.registered_at.desc())
            .offset(offset)
            .limit(query.page_size)
        )
        rows = (await self._session.execute(page_stmt)).scalars().all()
        return rows, int(total or 0)

    def _scope_conditions(self, scope: SearchScope) -> list[ColumnElement[bool]]:
        """Translate the caller's read scope into SQLAlchemy filter expressions.

        A caller without cross-team access sees only tickets in one of their teams, assigned to
        them, or registered by them. Callers not cleared for confidential tickets never see them.
        These conditions are ANDed with the user-supplied filters, so scope can only narrow results.

        Args:
            scope: The caller's read scope.

        Returns:
            A list of boolean SQL expressions enforcing the scope.
        """
        conditions: list[ColumnElement[bool]] = []
        if not scope.all_access:
            reachable: list[ColumnElement[bool]] = [
                Ticket.current_assignee_id == scope.subject,
                Ticket.registered_by == scope.subject,
            ]
            if scope.team_ids:
                reachable.append(Ticket.current_team_id.in_(scope.team_ids))
            conditions.append(or_(*reachable))
        if not scope.include_confidential:
            conditions.append(Ticket.is_confidential.is_(False))
        return conditions

    def _build_conditions(self, query: TicketSearchQuery) -> list[ColumnElement[bool]]:
        """Translate a search query into SQLAlchemy filter expressions.

        Party-scoped filters (identifier, full name) are expressed as an ``EXISTS`` sub-select on
        the applicant table, so a ticket appears once regardless of how many parties match.

        Args:
            query: The search filters.

        Returns:
            A list of boolean SQL expressions to AND together.
        """
        conditions: list[ColumnElement[bool]] = []
        if query.registration_number is not None:
            conditions.append(Ticket.registration_number == query.registration_number)
        if query.contract_number is not None:
            conditions.append(Ticket.contract_number == query.contract_number)
        if query.status_code is not None:
            conditions.append(Ticket.current_status_code == query.status_code)
        if query.stage_code is not None:
            conditions.append(Ticket.current_stage_code == query.stage_code)
        if query.product_code is not None:
            conditions.append(Ticket.product_code == query.product_code)
        if query.classifier_code is not None:
            conditions.append(Ticket.classifier_code == query.classifier_code)
        if query.channel_code is not None:
            conditions.append(Ticket.source_channel_code == query.channel_code)
        if query.assignee_id is not None:
            conditions.append(Ticket.current_assignee_id == query.assignee_id)
        if query.team_id is not None:
            conditions.append(Ticket.current_team_id == query.team_id)
        if query.received_from is not None:
            conditions.append(Ticket.received_at >= query.received_from)
        if query.received_to is not None:
            conditions.append(Ticket.received_at <= query.received_to)
        if query.registered_from is not None:
            conditions.append(Ticket.registered_at >= query.registered_from)
        if query.registered_to is not None:
            conditions.append(Ticket.registered_at <= query.registered_to)

        party_conditions = []
        if query.identifier_value is not None:
            party_conditions.append(TicketApplicant.identifier_value == query.identifier_value)
        if query.full_name is not None:
            party_conditions.append(TicketApplicant.full_name.ilike(f"%{query.full_name}%"))
        if party_conditions:
            conditions.append(
                select(TicketApplicant.id)
                .where(TicketApplicant.ticket_id == Ticket.id, *party_conditions)
                .exists()
            )
        return conditions


class CommentRepository:
    """Reads and writes ticket comments."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: The active database session.
        """
        self._session = session

    def add(self, comment: TicketComment) -> None:
        """Stage a new comment for insertion.

        Args:
            comment: The comment to add.
        """
        self._session.add(comment)

    async def list_for_ticket(self, ticket_id: uuid.UUID) -> Sequence[TicketComment]:
        """List a ticket's comments, newest first.

        Args:
            ticket_id: The owning ticket.

        Returns:
            The comments ordered by creation time descending.
        """
        result = await self._session.execute(
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at.desc())
        )
        return result.scalars().all()

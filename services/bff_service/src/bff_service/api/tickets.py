"""HTTP routes for the appeal gateway.

Search and card commands are forwarded verbatim to the Ticket Service after the gateway enforces the
required permission claim; the workspace route aggregates the card and comments (plus later-phase
placeholders) into one envelope. No business logic lives here (root ``CLAUDE.md``): the gateway
authorizes and relays, and the Ticket Service remains the authority on validation and invariants.
"""

# ruff: noqa: N803  # path params use camelCase to match the committed contract labels

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from mfo_http import PlatformHttpClient, read_bounded
from starlette.responses import Response

from bff_service.api.dependencies import (
    AuthenticatedCaller,
    build_problem,
    get_settings_dep,
    get_ticket_client,
    require_permission,
)
from bff_service.api.proxy import (
    PayloadTooLargeError,
    forward_headers,
    payload_too_large_response,
    read_body_bounded,
    relay,
)
from bff_service.api.schemas import WorkspaceResponse, workspace_to_response
from bff_service.application.workspace import (
    WorkspaceForbiddenError,
    WorkspaceRateLimitedError,
    WorkspaceTicketNotFoundError,
    WorkspaceUnauthorizedError,
    WorkspaceUpstreamError,
    build_workspace,
)
from bff_service.config import Settings
from bff_service.domain.permissions import TicketPermission

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


async def _forward_command(
    ticket_client: PlatformHttpClient,
    request: Request,
    settings: Settings,
    caller: AuthenticatedCaller,
    method: str,
    path: str,
    *,
    idempotency_key: str | None = None,
) -> Response:
    """Forward a bounded request body to the Ticket Service and relay its bounded response.

    The incoming body is read under an ingress ceiling and rejected with ``413`` before it is fully
    buffered or forwarded, so an oversized mutation never reaches the Ticket Service. The downstream
    response is streamed under an egress ceiling (CR-BFF-R6-HIGH-001).

    Args:
        ticket_client: The Ticket Service HTTP client.
        request: The incoming request, whose raw body is forwarded.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller whose token is forwarded downstream.
        method: The HTTP method to use downstream.
        path: The downstream request path.
        idempotency_key: Optional idempotency key to forward.

    Returns:
        The relayed Ticket Service response, or a ``413`` when the request body is too large.
    """
    try:
        body = await read_body_bounded(request, settings.max_request_bytes)
    except PayloadTooLargeError:
        # Reject before any downstream call: an unsafe mutation is never partially forwarded.
        return payload_too_large_response()
    headers = forward_headers(caller.token, idempotency_key=idempotency_key)
    headers["content-type"] = request.headers.get("content-type", "application/json")
    bounded = await read_bounded(
        ticket_client,
        method,
        path,
        max_bytes=settings.max_response_bytes,
        content=body,
        headers=headers,
    )
    return relay(bounded, "ticket")


@router.get("", operation_id="searchTickets")
async def search_tickets(
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.READ.value))
    ],
) -> Response:
    """Search appeals, forwarding the query parameters to the Ticket Service under a bounded read.

    Args:
        request: The incoming request, whose query parameters are forwarded.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (egress byte ceiling).
        caller: The authenticated caller (requires ticket:read).

    Returns:
        The relayed paginated search result.
    """
    bounded = await read_bounded(
        ticket_client,
        "GET",
        "/api/v1/tickets",
        max_bytes=settings.max_response_bytes,
        params=dict(request.query_params),
        headers=forward_headers(caller.token),
    )
    return relay(bounded, "ticket")


@router.post(
    "",
    operation_id="createTicket",
)
async def create_ticket(
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.CREATE.value))
    ],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    """Register an appeal, forwarding the body and any idempotency key to the Ticket Service.

    Args:
        request: The incoming request, whose body carries the registration.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:create).
        idempotency_key: Optional key making the registration retry-safe.

    Returns:
        The relayed registration response.
    """
    return await _forward_command(
        ticket_client,
        request,
        settings,
        caller,
        "POST",
        "/api/v1/tickets",
        idempotency_key=idempotency_key,
    )


@router.get(
    "/{ticketId}/workspace",
    response_model=WorkspaceResponse,
    operation_id="getTicketWorkspace",
)
async def get_ticket_workspace(
    ticketId: uuid.UUID,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.READ.value))
    ],
) -> WorkspaceResponse:
    """Aggregate the appeal workspace, flagging partial read failures.

    Args:
        ticketId: The appeal identifier.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (provides the total aggregation deadline).
        caller: The authenticated caller (requires ticket:read).

    Returns:
        The aggregated workspace, possibly degraded (only for the optional comments section).

    Raises:
        ProblemDetailError: 401/403 on a downstream auth failure, 404 when the appeal does not
            exist, 429 when rate limited, or 502/503/504 on a critical card failure — never a masked
            200.
    """
    try:
        # A total budget for the concurrent aggregation, distinct from the per-call HTTP timeouts.
        async with asyncio.timeout(settings.workspace_deadline_seconds):
            workspace = await build_workspace(ticket_client, ticketId, caller.token)
    except TimeoutError as exc:
        raise build_problem(
            504, "Upstream timeout", "the workspace aggregation exceeded its time budget"
        ) from exc
    except WorkspaceUnauthorizedError as exc:
        raise build_problem(
            401,
            "Not authenticated",
            "the workspace read was not authenticated",
            www_authenticate=True,
        ) from exc
    except WorkspaceForbiddenError as exc:
        raise build_problem(403, "Forbidden", "access to the appeal was denied") from exc
    except WorkspaceTicketNotFoundError as exc:
        raise build_problem(404, "Ticket not found", f"appeal {ticketId} does not exist") from exc
    except WorkspaceRateLimitedError as exc:
        headers = {"Retry-After": exc.retry_after} if exc.retry_after is not None else None
        raise build_problem(
            429, "Too many requests", "the workspace read was rate limited", headers=headers
        ) from exc
    except WorkspaceUpstreamError as exc:
        raise build_problem(exc.status, "Upstream error", str(exc)) from exc
    return workspace_to_response(workspace)


@router.patch(
    "/{ticketId}",
    operation_id="updateTicket",
)
async def update_ticket(
    ticketId: uuid.UUID,
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.UPDATE.value))
    ],
) -> Response:
    """Update editable appeal-card details via the Ticket Service.

    Args:
        ticketId: The appeal identifier.
        request: The incoming request, whose body carries the partial update.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:update).

    Returns:
        The relayed updated card.
    """
    return await _forward_command(
        ticket_client, request, settings, caller, "PATCH", f"/api/v1/tickets/{ticketId}"
    )


@router.post(
    "/{ticketId}/classify",
    operation_id="classifyTicket",
)
async def classify_ticket(
    ticketId: uuid.UUID,
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.CLASSIFY.value))
    ],
) -> Response:
    """Set an appeal's classification via the Ticket Service.

    Args:
        ticketId: The appeal identifier.
        request: The incoming request, whose body carries the classification.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:classify).

    Returns:
        The relayed reclassified card.
    """
    return await _forward_command(
        ticket_client, request, settings, caller, "POST", f"/api/v1/tickets/{ticketId}/classify"
    )


@router.post(
    "/{ticketId}/decision",
    operation_id="recordDecision",
)
async def record_decision(
    ticketId: uuid.UUID,
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.DECIDE.value))
    ],
) -> Response:
    """Record the decision on an appeal via the Ticket Service.

    Args:
        ticketId: The appeal identifier.
        request: The incoming request, whose body carries the decision.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:decide).

    Returns:
        The relayed card with the recorded decision.
    """
    return await _forward_command(
        ticket_client, request, settings, caller, "POST", f"/api/v1/tickets/{ticketId}/decision"
    )


@router.post(
    "/{ticketId}/close",
    operation_id="closeTicket",
)
async def close_ticket(
    ticketId: uuid.UUID,
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.CLOSE.value))
    ],
) -> Response:
    """Close an appeal via the Ticket Service.

    Args:
        ticketId: The appeal identifier.
        request: The incoming request, whose body carries the closure request.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:close).

    Returns:
        The relayed closed card.
    """
    return await _forward_command(
        ticket_client, request, settings, caller, "POST", f"/api/v1/tickets/{ticketId}/close"
    )


@router.post(
    "/{ticketId}/legal-hold",
    operation_id="setLegalHold",
)
async def set_legal_hold(
    ticketId: uuid.UUID,
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.LEGAL_HOLD.value))
    ],
) -> Response:
    """Set or clear the legal hold on an appeal via the Ticket Service.

    Args:
        ticketId: The appeal identifier.
        request: The incoming request, whose body carries the legal-hold request.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:legal_hold).

    Returns:
        The relayed card with the updated legal-hold flag.
    """
    return await _forward_command(
        ticket_client, request, settings, caller, "POST", f"/api/v1/tickets/{ticketId}/legal-hold"
    )


@router.post(
    "/{ticketId}/comments",
    operation_id="addComment",
)
async def add_comment(
    ticketId: uuid.UUID,
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.COMMENT.value))
    ],
) -> Response:
    """Add a comment to an appeal via the Ticket Service.

    Args:
        ticketId: The appeal identifier.
        request: The incoming request, whose body carries the comment.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (ingress/egress byte ceilings).
        caller: The authenticated caller (requires ticket:comment).

    Returns:
        The relayed created comment.
    """
    return await _forward_command(
        ticket_client, request, settings, caller, "POST", f"/api/v1/tickets/{ticketId}/comments"
    )

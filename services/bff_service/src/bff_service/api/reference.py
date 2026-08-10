"""HTTP route for reference-dictionary data.

The gateway forwards the reference-data request to the Ticket Service after enforcing the required
permission claim and relays the response verbatim. No business logic lives here (root
``CLAUDE.md``): the gateway authorizes and relays, and the Ticket Service remains the authority on
the reference catalog.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mfo_http import PlatformHttpClient, read_bounded
from starlette.responses import Response

from bff_service.api.dependencies import (
    AuthenticatedCaller,
    get_settings_dep,
    get_ticket_client,
    require_permission,
)
from bff_service.api.proxy import forward_headers, relay
from bff_service.config import Settings
from bff_service.domain.permissions import TicketPermission

router = APIRouter(prefix="/api/v1", tags=["tickets"])


@router.get("/reference-data", operation_id="listReferenceData")
async def list_reference_data(
    request: Request,
    ticket_client: Annotated[PlatformHttpClient, Depends(get_ticket_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    caller: Annotated[
        AuthenticatedCaller, Depends(require_permission(TicketPermission.READ.value))
    ],
) -> Response:
    """List active reference-dictionary entries via the Ticket Service under a bounded read.

    Args:
        request: The incoming request, whose query parameters (for example, ``types``) are
            forwarded.
        ticket_client: The Ticket Service HTTP client.
        settings: Application settings (egress byte ceiling).
        caller: The authenticated caller (requires ticket:read).

    Returns:
        The relayed reference-data response.
    """
    bounded = await read_bounded(
        ticket_client,
        "GET",
        "/api/v1/reference-data",
        max_bytes=settings.max_response_bytes,
        params=dict(request.query_params),
        headers=forward_headers(caller.token),
    )
    return relay(bounded, "ticket")

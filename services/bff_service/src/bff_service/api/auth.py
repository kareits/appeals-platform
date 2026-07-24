"""HTTP routes for authentication at the gateway.

``POST /auth/login`` is a public passthrough to the IAM dev/local login. ``GET /auth/me`` returns
the caller's resolved auth context (the subject, roles, and permissions the gateway authorizes on).
No business logic lives here (root ``CLAUDE.md``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from mfo_http import PlatformHttpClient, read_bounded
from starlette.responses import Response

from bff_service.api.dependencies import (
    AuthenticatedCaller,
    get_iam_client,
    get_settings_dep,
    require_auth_context,
)
from bff_service.api.proxy import (
    PayloadTooLargeError,
    payload_too_large_response,
    read_body_bounded,
    relay,
)
from bff_service.api.schemas import AuthContextResponse, auth_context_to_response
from bff_service.config import Settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_IAM_LOGIN_PATH = "/api/v1/auth/login"


@router.post("/login", operation_id="bffLogin")
async def login(
    request: Request,
    iam_client: Annotated[PlatformHttpClient, Depends(get_iam_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Response:
    """Authenticate by forwarding the credentials to the IAM dev/local login.

    The public login body is read under an ingress ceiling and rejected with ``413`` before it is
    fully buffered or forwarded; the IAM response is streamed under an egress ceiling and relayed
    (CR-BFF-R6-HIGH-001).

    Args:
        request: The incoming request, whose body carries the login credentials.
        iam_client: The IAM HTTP client.
        settings: Application settings (ingress/egress byte ceilings).

    Returns:
        The relayed IAM login response, or a ``413`` when the request body is too large.
    """
    try:
        body = await read_body_bounded(request, settings.max_request_bytes)
    except PayloadTooLargeError:
        return payload_too_large_response()
    content_type = request.headers.get("content-type", "application/json")
    bounded = await read_bounded(
        iam_client,
        "POST",
        _IAM_LOGIN_PATH,
        max_bytes=settings.max_response_bytes,
        content=body,
        headers={"content-type": content_type},
    )
    return relay(bounded, "identity")


@router.get(
    "/me",
    response_model=AuthContextResponse,
    operation_id="getAuthContext",
)
async def get_auth_context(
    caller: Annotated[AuthenticatedCaller, Depends(require_auth_context)],
) -> AuthContextResponse:
    """Return the caller's resolved auth context.

    Args:
        caller: The authenticated caller resolved from the bearer token.

    Returns:
        The subject, username, roles, and permissions the gateway authorizes on.
    """
    return auth_context_to_response(caller.context)

"""Auth-context resolution for the BFF gateway.

The gateway does not verify access tokens itself: it resolves the caller's context by calling the
IAM service's ``GET /api/v1/auth/me`` with the presented bearer token (project decision — "auth
context via IAM /auth/me"). This keeps token-signing material out of the gateway and keeps IAM the
single authority on claim resolution, which stays valid across the corporate OIDC transition
(ADR-AUTH-OIDC, TASK_06). The gateway then authorizes requests on the resolved permission claims.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from mfo_http import PlatformHttpClient, is_json_media_type, read_bounded

from bff_service.application.errors import (
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)

_AUTH_ME_PATH = "/api/v1/auth/me"
# Upper bound on the identity response the gateway will buffer; a larger body is a protocol failure,
# not a trusted identity document (CR-BFF-R6-HIGH-001).
_MAX_AUTH_CONTEXT_BYTES = 1_000_000


@dataclass(frozen=True)
class AuthContext:
    """The caller's resolved authorization context.

    Attributes:
        subject: The authenticated user's identifier.
        username: The authenticated user's login handle.
        roles: The role names granted to the user.
        permissions: The permission claim strings resolved from those roles.
    """

    subject: uuid.UUID
    username: str
    roles: tuple[str, ...]
    permissions: frozenset[str]

    def has_permission(self, permission: str) -> bool:
        """Return whether the context carries a given permission claim.

        Args:
            permission: The required permission claim string (``resource:action``).

        Returns:
            ``True`` when the permission is present.
        """
        return permission in self.permissions


def _parse_context(payload: object) -> AuthContext:
    """Build an :class:`AuthContext` from an IAM ``/auth/me`` payload, failing closed on bad shapes.

    Args:
        payload: The decoded JSON body returned by IAM.

    Returns:
        The resolved auth context.

    Raises:
        UpstreamProtocolError: When the payload is structurally not a valid subject document; the
            gateway cannot trust a malformed identity response (mapped to a safe 502).
    """
    if not isinstance(payload, dict):
        raise UpstreamProtocolError("iam", "identity response was not an object")
    try:
        subject = uuid.UUID(str(payload["subject"]))
        username = payload["username"]
        roles = payload["roles"]
        permissions = payload["permissions"]
    except (KeyError, ValueError) as exc:
        raise UpstreamProtocolError("iam", "identity response was malformed") from exc
    if not isinstance(username, str) or not _is_str_list(roles) or not _is_str_list(permissions):
        raise UpstreamProtocolError("iam", "identity response had invalid claim types")
    return AuthContext(
        subject=subject,
        username=username,
        roles=tuple(roles),
        permissions=frozenset(permissions),
    )


def _is_str_list(value: object) -> bool:
    """Return whether a value is a list of strings.

    Args:
        value: The value to check.

    Returns:
        ``True`` when the value is a list whose items are all strings.
    """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


async def resolve_auth_context(iam_client: PlatformHttpClient, token: str) -> AuthContext:
    """Resolve the caller's auth context by calling IAM ``/auth/me`` with the bearer token.

    The correlation ID is propagated automatically by the platform HTTP client.

    Args:
        iam_client: The HTTP client bound to the IAM service base URL.
        token: The caller's bearer access token (without the ``Bearer`` prefix).

    Returns:
        The resolved auth context.

    Raises:
        UpstreamAuthError: When IAM rejects the token (HTTP 401).
        UpstreamUnavailableError: When IAM is unreachable.
        UpstreamProtocolError: When IAM returns an unexpected status, media type, or malformed body.
    """
    # The identity response is streamed under a byte ceiling so a faulty/hostile IAM cannot make the
    # gateway buffer an unbounded body before it is validated (CR-BFF-R6-HIGH-001).
    bounded = await read_bounded(
        iam_client,
        "GET",
        _AUTH_ME_PATH,
        max_bytes=_MAX_AUTH_CONTEXT_BYTES,
        headers={"Authorization": f"Bearer {token}"},
    )
    if bounded.failure == "timeout":
        raise UpstreamUnavailableError("iam", "the identity service timed out")
    if bounded.failure == "connection":
        raise UpstreamUnavailableError("iam", "the identity service is unreachable")
    if bounded.status == 401:
        raise UpstreamAuthError("the identity service rejected the access token")
    if bounded.status != 200:
        raise UpstreamProtocolError("iam", f"the identity service returned status {bounded.status}")
    # A 200 must be bounded JSON of the expected shape; an oversized body, wrong media type, or
    # invalid JSON is malformed and must map to a safe 502, not a trusted identity (RR-HIGH-003).
    if bounded.oversized:
        raise UpstreamProtocolError("iam", "identity response was too large")
    if not is_json_media_type(bounded.headers.get("content-type")):
        raise UpstreamProtocolError("iam", "identity response was not JSON")
    try:
        payload = json.loads(bounded.content or b"")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpstreamProtocolError("iam", "identity response was not valid JSON") from exc
    return _parse_context(payload)

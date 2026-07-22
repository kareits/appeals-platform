"""Access-token issuing and verification for dev/local authentication.

Issues a signed JWT (HS256) whose claims carry the subject, username, roles, and resolved
permissions, so downstream services authorize on self-contained claims without calling IAM per
request. docs/06 targets signed-JWT verification in production; this symmetric dev scheme is
forward-compatible with the corporate OIDC transition (ADR-AUTH-OIDC, TASK_06), which will swap the
signing key material and issuer without changing the claim shape.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt


@dataclass(frozen=True)
class TokenClaims:
    """Decoded, validated claims of an access token.

    Attributes:
        subject: The user's internal identifier (the ``sub`` claim).
        username: The user's login handle.
        roles: The role names granted to the user.
        permissions: The permission strings resolved from those roles.
    """

    subject: uuid.UUID
    username: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


class TokenError(Exception):
    """Raised when a token cannot be issued or fails verification."""


def _string_array(value: object, claim: str) -> tuple[str, ...]:
    """Validate that a claim is an array of strings and return it as a tuple.

    Args:
        value: The raw claim value.
        claim: The claim name, for error messages.

    Returns:
        The claim as a tuple of strings.

    Raises:
        TokenError: If the value is not a list of strings.
    """
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TokenError(f"token has an invalid {claim} claim")
    return tuple(value)


@dataclass(frozen=True)
class TokenIssuer:
    """Issues and verifies HS256 access tokens for dev/local auth.

    Attributes:
        secret: The symmetric signing secret.
        algorithm: The JWS algorithm (HS256 for the dev scheme).
        issuer: The ``iss`` claim value.
        audience: The ``aud`` claim value.
        ttl_seconds: Token lifetime in seconds.
    """

    secret: str
    algorithm: str
    issuer: str
    audience: str
    ttl_seconds: int

    def issue(
        self,
        *,
        subject: uuid.UUID,
        username: str,
        roles: list[str],
        permissions: list[str],
    ) -> tuple[str, int]:
        """Issue a signed access token carrying the subject's roles and permissions.

        Args:
            subject: The user's internal identifier.
            username: The user's login handle.
            roles: The role names granted to the user.
            permissions: The permission strings resolved from those roles.

        Returns:
            A tuple of the encoded token and its lifetime in seconds.
        """
        now = datetime.now(UTC)
        payload = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": str(subject),
            "username": username,
            "roles": roles,
            "permissions": permissions,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.ttl_seconds)).timestamp()),
        }
        token = jwt.encode(payload, self.secret, algorithm=self.algorithm)
        return token, self.ttl_seconds

    def verify(self, token: str) -> TokenClaims:
        """Verify a token's signature, issuer, audience, and expiry, returning its claims.

        Args:
            token: The encoded access token.

        Returns:
            The validated token claims.

        Raises:
            TokenError: If the token is malformed, expired, or fails validation.
        """
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                issuer=self.issuer,
                audience=self.audience,
            )
        except jwt.InvalidTokenError as exc:
            raise TokenError(str(exc)) from exc
        try:
            subject = uuid.UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise TokenError("token is missing a valid subject") from exc
        # Fail closed on structurally invalid claims: a signed token whose ``roles``/``permissions``
        # are not string arrays (for example ``roles: "ADMIN"``) must be rejected as a 401, not
        # coerced character-by-character or allowed to raise a 500 downstream (CR-IAM-MEDIUM-005).
        username = payload.get("username")
        if not isinstance(username, str):
            raise TokenError("token has an invalid username claim")
        roles = _string_array(payload.get("roles", []), "roles")
        permissions = _string_array(payload.get("permissions", []), "permissions")
        return TokenClaims(
            subject=subject,
            username=username,
            roles=roles,
            permissions=permissions,
        )

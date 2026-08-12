"""Independent access-token verification for the document service.

The document service is a security boundary in its own right: it serves file bytes, so an internal
caller reaching it directly (bypassing the BFF) must still present a valid signed token. This module
verifies the JWT the IAM service issues, but implements verification independently — it does not
import IAM code or read the IAM database (ADR-004, ADR-007). The claim shape (subject, username,
roles, permissions, teams) is a stable wire contract shared by string value only.

Verification pins a fixed algorithm allowlist (no ``alg=none`` and no algorithm confusion), and
checks the signature, issuer, audience, expiry, and the structural types of every claim. Anything
malformed fails closed as a :class:`TokenError`, which the API maps to 401.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt


@dataclass(frozen=True)
class DocumentClaims:
    """Decoded, validated claims of an access token.

    Attributes:
        subject: The caller's internal identifier (the ``sub`` claim); the server-trusted actor
            recorded as the uploader.
        username: The caller's login handle.
        roles: The role names granted to the caller.
        permissions: The permission claim strings resolved from those roles.
        teams: Identifiers of the teams the caller belongs to.
    """

    subject: uuid.UUID
    username: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    teams: tuple[str, ...]

    def has_permission(self, permission: str) -> bool:
        """Return whether the caller holds a given permission claim.

        Args:
            permission: The required permission claim string (``resource:action``).

        Returns:
            ``True`` when the permission is present.
        """
        return permission in self.permissions


class TokenError(Exception):
    """Raised when a token is missing, malformed, or fails verification."""


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
class TokenVerifier:
    """Verifies HS256 access tokens issued by the IAM service.

    Attributes:
        secret: The symmetric signing secret shared with IAM (dev/local scheme, docs/06).
        algorithms: The fixed allowlist of accepted JWS algorithms (no ``none``).
        issuer: The expected ``iss`` claim value.
        audience: The expected ``aud`` claim value.
    """

    secret: str
    algorithms: tuple[str, ...]
    issuer: str
    audience: str

    def verify(self, token: str) -> DocumentClaims:
        """Verify a token's signature, issuer, audience, and expiry, returning its claims.

        Args:
            token: The encoded access token (without the ``Bearer`` prefix).

        Returns:
            The validated token claims.

        Raises:
            TokenError: If the token is malformed, expired, wrongly signed, or has invalid claims.
        """
        try:
            payload = jwt.decode(
                token,
                self.secret,
                # The explicit allowlist is the primary defence against ``alg=none`` and
                # HS/RS confusion: PyJWT rejects any token whose header algorithm is not listed.
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError as exc:
            raise TokenError(str(exc)) from exc
        try:
            subject = uuid.UUID(str(payload["sub"]))
        except (KeyError, ValueError) as exc:
            raise TokenError("token is missing a valid subject") from exc
        username = payload.get("username")
        if not isinstance(username, str):
            raise TokenError("token has an invalid username claim")
        roles = _string_array(payload.get("roles", []), "roles")
        permissions = _string_array(payload.get("permissions", []), "permissions")
        teams = _string_array(payload.get("teams", []), "teams")
        return DocumentClaims(
            subject=subject,
            username=username,
            roles=roles,
            permissions=permissions,
            teams=teams,
        )

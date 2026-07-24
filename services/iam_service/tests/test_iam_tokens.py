"""Unit tests for access-token issuing and verification."""

from __future__ import annotations

import uuid

import jwt
import pytest
from iam_service.infrastructure.tokens import TokenError, TokenIssuer


def _issuer(secret: str = "unit-secret-0123456789-abcdefghij") -> TokenIssuer:
    """Build a token issuer for tests.

    Args:
        secret: The signing secret.

    Returns:
        A configured issuer.
    """
    return TokenIssuer(
        secret=secret,
        algorithm="HS256",
        issuer="mfo-iam",
        audience="mfo-appeals",
        ttl_seconds=3600,
    )


def test_issue_and_verify_roundtrip() -> None:
    """A freshly issued token verifies and carries its claims."""
    issuer = _issuer()
    subject = uuid.uuid4()
    team = uuid.uuid4()
    token, ttl = issuer.issue(
        subject=subject,
        username="employee",
        roles=["EMPLOYEE"],
        permissions=["ticket:read"],
        teams=[str(team)],
    )
    assert ttl == 3600
    claims = issuer.verify(token)
    assert claims.subject == subject
    assert claims.username == "employee"
    assert claims.roles == ("EMPLOYEE",)
    assert claims.permissions == ("ticket:read",)
    assert claims.teams == (str(team),)


def test_verify_rejects_wrong_secret() -> None:
    """A token signed with another secret fails verification."""
    token, _ = _issuer("secret-one-0123456789-abcdefghij").issue(
        subject=uuid.uuid4(), username="u", roles=[], permissions=[], teams=[]
    )
    with pytest.raises(TokenError):
        _issuer("secret-two-0123456789-abcdefghij").verify(token)


def test_verify_rejects_garbage() -> None:
    """A malformed token string fails verification."""
    with pytest.raises(TokenError):
        _issuer().verify("not-a-jwt")


def test_verify_rejects_non_array_roles_claim() -> None:
    """A validly signed token whose roles claim is a string (not an array) is rejected."""
    issuer = _issuer()
    payload = {
        "iss": "mfo-iam",
        "aud": "mfo-appeals",
        "sub": str(uuid.uuid4()),
        "username": "someone",
        "roles": "ADMIN",  # malformed: must be an array of strings
        "permissions": ["iam:manage"],
        "iat": 0,
        "exp": 9_999_999_999,
    }
    token = jwt.encode(payload, issuer.secret, algorithm=issuer.algorithm)
    with pytest.raises(TokenError):
        issuer.verify(token)


def test_verify_rejects_non_string_username_claim() -> None:
    """A validly signed token whose username claim is not a string is rejected."""
    issuer = _issuer()
    payload = {
        "iss": "mfo-iam",
        "aud": "mfo-appeals",
        "sub": str(uuid.uuid4()),
        "username": 123,  # malformed: must be a string
        "roles": ["ADMIN"],
        "permissions": ["iam:manage"],
        "iat": 0,
        "exp": 9_999_999_999,
    }
    token = jwt.encode(payload, issuer.secret, algorithm=issuer.algorithm)
    with pytest.raises(TokenError):
        issuer.verify(token)

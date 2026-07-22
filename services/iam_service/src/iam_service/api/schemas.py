"""Pydantic request/response schemas for the IAM API.

All models serialize with camelCase field names (docs/05). Request models are strict (unknown
properties rejected) so the runtime schema matches the committed contract. Passwords appear only in
request models and are never echoed in a response.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

from iam_service.domain.permissions import resolve_permissions
from iam_service.domain.roles import Role
from iam_service.infrastructure.models import User

# Bounded input types aligned with the database column limits and the OpenAPI contract, so
# oversized/blank input is rejected with 422 by Pydantic rather than failing only in PostgreSQL.
NameStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
# bcrypt truncates beyond 72 bytes; cap login input at 72 and require at least 8 for new passwords.
LoginPasswordStr = Annotated[str, StringConstraints(min_length=1, max_length=72)]
NewPasswordStr = Annotated[str, StringConstraints(min_length=8, max_length=72)]
EmailStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class RequestModel(BaseModel):
    """Strict base for HTTP request bodies (camelCase-only input, unknown properties rejected)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid")


class ResponseModel(BaseModel):
    """Base for HTTP responses: camelCase output, snake_case construction by the mappers."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(RequestModel):
    """Dev/local login credentials.

    Attributes:
        username: The login handle.
        password: The plaintext password (verified against the stored bcrypt hash).
    """

    username: NameStr
    password: LoginPasswordStr


class TokenResponse(ResponseModel):
    """A signed access token and the claims it carries.

    Attributes:
        access_token: The signed JWT access token.
        token_type: The token type (always ``Bearer``).
        expires_in: Token lifetime in seconds.
        subject: The authenticated user's identifier.
        username: The authenticated user's login handle.
        roles: The user's granted roles.
        permissions: Permission claims resolved from the user's roles.
    """

    # Always set explicitly by the route (never defaulted) so the runtime schema marks it required,
    # matching the committed contract (CR-IAM-MEDIUM-001).
    access_token: str
    token_type: str
    expires_in: int
    subject: uuid.UUID
    username: str
    roles: list[Role]
    permissions: list[str]


class SubjectResponse(ResponseModel):
    """The claims of the currently authenticated subject.

    Attributes:
        subject: The subject's identifier.
        username: The subject's login handle.
        roles: The subject's granted roles.
        permissions: The subject's resolved permission claims.
    """

    subject: uuid.UUID
    username: str
    roles: list[Role]
    permissions: list[str]


class CreateUserRequest(RequestModel):
    """Input to create a user with initial role grants.

    Attributes:
        username: Unique login handle.
        full_name: Display name.
        password: Initial plaintext password (hashed before storage).
        email: Optional contact email.
        team_id: Optional owning team.
        roles: Initial role grants (may be empty).
    """

    username: NameStr
    full_name: NameStr
    password: NewPasswordStr
    email: EmailStr | None = None
    team_id: uuid.UUID | None = None
    roles: list[Role] = Field(default_factory=list)


class AssignRoleRequest(RequestModel):
    """Input to grant a role to a user.

    Attributes:
        role: The role to grant.
    """

    role: Role


class UserResponse(ResponseModel):
    """A user with role grants and resolved permissions.

    Attributes:
        id: Internal user identifier.
        username: Login handle.
        full_name: Display name.
        email: Contact email, if any.
        is_active: Whether the account may authenticate.
        team_id: Owning team, if any.
        roles: Granted roles.
        permissions: Permission claims resolved from the granted roles.
        version: Optimistic-locking version.
    """

    id: uuid.UUID
    username: str
    full_name: str
    email: str | None
    is_active: bool
    team_id: uuid.UUID | None
    roles: list[Role]
    permissions: list[str]
    version: int


def user_to_response(user: User) -> UserResponse:
    """Map a user ORM row to its API response, resolving permissions from roles.

    Args:
        user: The user to map.

    Returns:
        The API response model.
    """
    roles = sorted((grant.role for grant in user.roles), key=lambda role: role.value)
    permissions = sorted(permission.value for permission in resolve_permissions(set(roles)))
    return UserResponse(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        is_active=user.is_active,
        team_id=user.team_id,
        roles=roles,
        permissions=permissions,
        version=user.version,
    )

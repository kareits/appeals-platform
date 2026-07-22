"""Command objects for IAM use cases.

Commands are plain, framework-free dataclasses so the API layer can translate validated requests
into use-case inputs without the application layer depending on FastAPI or Pydantic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from iam_service.domain.roles import Role


@dataclass(frozen=True)
class CreateUserCommand:
    """Input to create a user with initial role grants.

    Attributes:
        username: Unique login handle.
        full_name: Display name.
        password: Plaintext password (hashed before storage; never persisted or logged).
        email: Optional contact email.
        team_id: Optional owning team.
        roles: Initial role grants (may be empty).
    """

    username: str
    full_name: str
    password: str
    email: str | None = None
    team_id: uuid.UUID | None = None
    roles: tuple[Role, ...] = field(default_factory=tuple)

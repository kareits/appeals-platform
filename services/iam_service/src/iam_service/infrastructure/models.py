"""SQLAlchemy models owned by the IAM service.

These tables realize the identity data the service owns (root ``CLAUDE.md`` data ownership): users,
teams, per-user role grants, and an audit log for security-relevant identity changes (docs/06).
Passwords are stored only as bcrypt hashes for the temporary dev/local auth (docs/06); no plaintext
credential is persisted. The user row carries an optimistic-locking ``version`` column.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from iam_service.domain.roles import Role
from iam_service.infrastructure.ids import uuid7

_CODE_LEN = 64
_NAME_LEN = 255


class Base(DeclarativeBase):
    """Declarative base for IAM-service ORM models."""


class Team(Base):
    """An organizational team a user can belong to.

    Attributes:
        id: Internal UUIDv7 primary key.
        code: Stable, unique team code.
        name: Human-facing team name (business content; may be Russian/Kazakh).
        created_at: Row creation timestamp (UTC).
    """

    __tablename__ = "iam_team"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(_CODE_LEN), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class User(Base):
    """A platform user with credentials and role grants.

    The ``password_hash`` holds a bcrypt hash for temporary dev/local auth only (docs/06); no shared
    accounts are used. Roles are stored as separate grant rows so a user may hold several.

    Attributes:
        id: Internal UUIDv7 primary key.
        username: Unique login handle.
        full_name: Display name.
        email: Optional contact email.
        password_hash: bcrypt password hash for dev/local auth.
        is_active: Whether the account may authenticate.
        team_id: Optional owning team.
        version: Optimistic-locking counter.
        created_at: Row creation timestamp (UTC).
        roles: The user's role grants.
    """

    __tablename__ = "iam_user"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    username: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False)
    email: Mapped[str | None] = mapped_column(String(_NAME_LEN), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(_NAME_LEN), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("iam_team.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    __mapper_args__ = {"version_id_col": version}


class UserRole(Base):
    """A single role grant to a user.

    A user may hold multiple roles; the ``(user_id, role)`` pair is unique so a role cannot be
    granted twice.

    Attributes:
        id: Internal UUIDv7 primary key.
        user_id: The user the role is granted to.
        role: The granted platform role.
        granted_at: When the grant was recorded (UTC).
        user: The owning user relationship.
    """

    __tablename__ = "iam_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_iam_user_role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("iam_user.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="iam_role"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="roles")


class AuditLog(Base):
    """Security-relevant identity actions recorded for audit (docs/06).

    Captures logins and role changes so administrative actions are attributable. ``details`` carries
    only non-sensitive context (never plaintext credentials).

    Attributes:
        id: Internal UUIDv7 primary key.
        entity_type: The kind of entity acted upon (for example, ``user``).
        entity_id: Identifier of the entity acted upon.
        action: The audited action code.
        actor_id: Identifier of the actor, if known.
        correlation_id: Correlation ID of the originating request, if present.
        details: Non-sensitive structured context.
        created_at: When the action was recorded (UTC).
    """

    __tablename__ = "iam_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid7)
    entity_type: Mapped[str] = mapped_column(String(_CODE_LEN), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    action: Mapped[str] = mapped_column(String(_CODE_LEN), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(_NAME_LEN), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

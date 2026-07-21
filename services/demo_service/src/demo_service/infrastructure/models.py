"""SQLAlchemy models owned by the demo service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for demo-service ORM models."""


class BootstrapMarker(Base):
    """A trivial table proving that migrations and persistence work end to end.

    Attributes:
        id: Surrogate primary key.
        name: A unique human-readable marker name.
        created_at: Server-assigned creation timestamp.
    """

    __tablename__ = "bootstrap_marker"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

"""SQLAlchemy declarative base for the BFF service.

The gateway owns no domain data, so its metadata declares no tables in EP-1 (TASK_01E-1). The base
exists to give Alembic a metadata target and to reserve the service's own database/schema per the
data-ownership boundary (ADR-004); tables are added only if the gateway later needs persistent state
(for example, rate-limit counters or session data).
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for the BFF service's (currently empty) schema."""

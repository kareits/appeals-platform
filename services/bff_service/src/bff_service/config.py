"""Runtime configuration for the BFF service.

Settings are loaded from environment variables (prefix ``BFF_``) with local-friendly defaults so the
service runs without external infrastructure during EP-1. The gateway is stateless with respect to
domain data; it keeps its own (currently empty) database only to satisfy the per-service schema
boundary (ADR-004), and it reaches the IAM and Ticket services over HTTP.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote

import httpx
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# A bounded, positive, finite number of seconds for a timeout setting. ``gt=0`` rejects
# zero/negative values; ``le`` caps absurd values; the validator rejects NaN/inf so timeout
# protection cannot be silently disabled (CR-BFF-MEDIUM-002).
_Seconds = Annotated[float, Field(gt=0, le=300)]


class Settings(BaseSettings):
    """Environment-driven settings for the BFF service.

    Attributes:
        environment: The deployment environment name (for example, ``local`` or ``test``).
        database_url: The SQLAlchemy async database URL for the gateway's own (empty) schema.
        iam_base_url: Base URL of the IAM service, used to resolve the auth context and proxy login.
        ticket_base_url: Base URL of the Ticket Service, used for search, commands, and workspace
            aggregation.
        http_connect_timeout_seconds: Per-call connect timeout for downstream requests.
        http_read_timeout_seconds: Per-call read timeout for downstream requests.
        http_write_timeout_seconds: Per-call write timeout for downstream requests.
        http_pool_timeout_seconds: Timeout waiting for a free pooled connection.
        workspace_deadline_seconds: Total request budget for the concurrent workspace aggregation,
            distinct from the per-call timeouts.
    """

    model_config = SettingsConfigDict(env_prefix="BFF_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./bff_service.db"
    # Discrete PostgreSQL connection parts. When host/user/name are all set, the URL is built with a
    # percent-encoded password so a URI-reserved character in a secret cannot corrupt it
    # (CR-BFF-R3-MEDIUM-003); otherwise ``database_url`` is used (local SQLite/dev).
    db_host: str | None = None
    db_port: int = 5432
    db_user: str | None = None
    db_password: str | None = None
    db_name: str | None = None
    iam_base_url: str = "http://localhost:8000"
    ticket_base_url: str = "http://localhost:8000"
    # Optional override for the committed OpenAPI contract path served as the runtime schema; when
    # unset it is auto-discovered relative to the repository/image (CR-BFF-R4-MEDIUM-001).
    openapi_contract_path: str | None = None
    http_connect_timeout_seconds: _Seconds = 5.0
    http_read_timeout_seconds: _Seconds = 10.0
    http_write_timeout_seconds: _Seconds = 10.0
    http_pool_timeout_seconds: _Seconds = 5.0
    workspace_deadline_seconds: _Seconds = 15.0
    # Ingress/egress byte ceilings enforced before full buffering (CR-BFF-R6-HIGH-001). Requests are
    # small JSON commands, so the ingress ceiling is tight; the egress ceiling bounds relayed data.
    max_request_bytes: Annotated[int, Field(gt=0, le=100_000_000)] = 1_000_000
    max_response_bytes: Annotated[int, Field(gt=0, le=100_000_000)] = 2_000_000

    @field_validator(
        "http_connect_timeout_seconds",
        "http_read_timeout_seconds",
        "http_write_timeout_seconds",
        "http_pool_timeout_seconds",
        "workspace_deadline_seconds",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        """Reject a non-finite timeout so timeout protection is never silently disabled.

        Args:
            value: The candidate timeout in seconds.

        Returns:
            The validated value.

        Raises:
            ValueError: If the value is NaN or infinite.
        """
        if not math.isfinite(value):
            raise ValueError("timeout settings must be finite")
        return value

    def resolved_database_url(self) -> str:
        """Return the async database URL, building it safely from discrete parts when provided.

        When ``db_host``/``db_user``/``db_name`` are set, the URL is built with a percent-encoded
        user and password so a secret containing URI-reserved characters cannot change URL parsing
        (R3-MEDIUM-003). Otherwise ``database_url`` is used as-is (local SQLite/dev).

        Returns:
            The resolved SQLAlchemy async database URL.
        """
        if self.db_host and self.db_user and self.db_name:
            user = quote(self.db_user, safe="")
            password = quote(self.db_password or "", safe="")
            netloc = f"{user}:{password}@{self.db_host}:{self.db_port}"
            return f"postgresql+asyncpg://{netloc}/{self.db_name}"
        return self.database_url

    def http_timeout(self) -> httpx.Timeout:
        """Build the per-call HTTPX timeout from the connect/read/write/pool settings.

        Returns:
            The configured HTTPX timeout.
        """
        return httpx.Timeout(
            connect=self.http_connect_timeout_seconds,
            read=self.http_read_timeout_seconds,
            write=self.http_write_timeout_seconds,
            pool=self.http_pool_timeout_seconds,
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

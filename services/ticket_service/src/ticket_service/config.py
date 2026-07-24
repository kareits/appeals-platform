"""Runtime configuration for the ticket service.

Settings are loaded from environment variables (prefix ``TICKET_``) with local-friendly defaults so
the service runs without external infrastructure during EP-1.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the ticket service.

    Attributes:
        environment: The deployment environment name (for example, ``local`` or ``test``).
        database_url: The SQLAlchemy async database URL.
        registration_number_prefix: Prefix for generated business registration numbers. Vendor
            neutral by default (ADR-016); the value is business-facing and may be changed per
            deployment without touching code.
        outbox_relay_enabled: Whether to run the background outbox relay that publishes staged
            events to RabbitMQ. Disabled by default so local runs and tests need no broker; the
            compose stack enables it.
        rabbitmq_url: AMQP connection URL used by the outbox relay when enabled.
        rabbitmq_exchange: Topic exchange the relay publishes events to.
        outbox_relay_interval_seconds: Delay between outbox relay passes.
        platform_timezone: IANA business timezone for date/working-hours computation (retention
            dates, SLA calendars). Timestamps are stored in UTC (ADR-003); this only affects
            business-date math. Read from the platform-wide ``PLATFORM_TIMEZONE`` variable (shared
            across services) or the service-scoped ``TICKET_PLATFORM_TIMEZONE``.
        jwt_secret: Symmetric secret used to verify access tokens issued by IAM (dev/local scheme,
            docs/06). The default is an insecure placeholder for local runs and tests only; the
            compose stack and any shared deployment must supply a strong secret matching IAM's.
        jwt_algorithms: Fixed allowlist of accepted JWS algorithms. Pinned to HS256 for the dev
            scheme; the allowlist is the primary defence against ``alg=none``/algorithm confusion.
        jwt_issuer: The expected token ``iss`` claim (IAM's issuer).
        jwt_audience: The expected token ``aud`` claim.
        db_host: Optional PostgreSQL host. When host/user/name are all set, the connection URL is
            built from these discrete parts with a percent-encoded password, so a secret containing
            URI-reserved characters (``:@/?#``) can never corrupt the URL (CR-BFF-R3-MEDIUM-003).
            When unset, ``database_url`` is used directly (local SQLite/dev).
        db_port: PostgreSQL port used with the discrete parts.
        db_user: PostgreSQL user used with the discrete parts.
        db_password: PostgreSQL password used with the discrete parts (percent-encoded in the URL).
        db_name: PostgreSQL database name used with the discrete parts.
    """

    model_config = SettingsConfigDict(env_prefix="TICKET_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./ticket_service.db"
    db_host: str | None = None
    db_port: int = 5432
    db_user: str | None = None
    db_password: str | None = None
    db_name: str | None = None
    registration_number_prefix: str = "AP"
    outbox_relay_enabled: bool = False
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "appeals.events"
    outbox_relay_interval_seconds: float = 2.0
    platform_timezone: str = Field(
        default="Asia/Almaty",
        validation_alias=AliasChoices("PLATFORM_TIMEZONE", "TICKET_PLATFORM_TIMEZONE"),
    )
    # TODO(TASK_06B): Replace the shared symmetric secret with corporate OIDC / asymmetric key
    # verification (JWKS) and remove the insecure default once secret management and the IdP exist.
    jwt_secret: str = "dev-insecure-secret-change-me-please"
    jwt_algorithms: tuple[str, ...] = ("HS256",)
    jwt_issuer: str = "mfo-iam"
    jwt_audience: str = "mfo-appeals"

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


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

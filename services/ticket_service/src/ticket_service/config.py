"""Runtime configuration for the ticket service.

Settings are loaded from environment variables (prefix ``TICKET_``) with local-friendly defaults so
the service runs without external infrastructure during EP-1.
"""

from __future__ import annotations

from functools import lru_cache

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
    """

    model_config = SettingsConfigDict(env_prefix="TICKET_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./ticket_service.db"
    registration_number_prefix: str = "AP"
    outbox_relay_enabled: bool = False
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "appeals.events"
    outbox_relay_interval_seconds: float = 2.0
    platform_timezone: str = Field(
        default="Asia/Almaty",
        validation_alias=AliasChoices("PLATFORM_TIMEZONE", "TICKET_PLATFORM_TIMEZONE"),
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

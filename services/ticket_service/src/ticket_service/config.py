"""Runtime configuration for the ticket service.

Settings are loaded from environment variables (prefix ``TICKET_``) with local-friendly defaults so
the service runs without external infrastructure during EP-1.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the ticket service.

    Attributes:
        environment: The deployment environment name (for example, ``local`` or ``test``).
        database_url: The SQLAlchemy async database URL.
        registration_number_prefix: Prefix for generated business registration numbers. Vendor
            neutral by default (ADR-016); the value is business-facing and may be changed per
            deployment without touching code.
    """

    model_config = SettingsConfigDict(env_prefix="TICKET_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./ticket_service.db"
    registration_number_prefix: str = "AP"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

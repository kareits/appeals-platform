"""Runtime configuration for the demo service.

Settings are loaded from environment variables (prefix ``DEMO_``) with local-friendly defaults so
the service runs without external infrastructure during TASK_00A.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the demo service.

    Attributes:
        environment: The deployment environment name (for example, ``local`` or ``test``).
        database_url: The SQLAlchemy async database URL.
    """

    model_config = SettingsConfigDict(env_prefix="DEMO_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./demo_service.db"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

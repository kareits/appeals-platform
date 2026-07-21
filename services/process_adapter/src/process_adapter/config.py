"""Runtime configuration for the Process Adapter service.

Settings are loaded from environment variables (prefix ``PA_``). Defaults target the Flowable
container inside the compose network.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the Process Adapter.

    Attributes:
        environment: The deployment environment name.
        flowable_base_url: Base URL of the Flowable REST service.
        flowable_username: Username for Flowable REST basic authentication.
        flowable_password: Password for Flowable REST basic authentication.
    """

    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: str = "local"
    flowable_base_url: str = "http://flowable:8080/flowable-rest/service"
    flowable_username: str = "rest-admin"
    flowable_password: str = "test"


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

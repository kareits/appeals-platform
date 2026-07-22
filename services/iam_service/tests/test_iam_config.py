"""Tests for environment-guarded dev-auth configuration (CR-IAM-HIGH-002)."""

from __future__ import annotations

import pytest
from iam_service.config import INSECURE_DEFAULT_SECRET, InsecureDevAuthConfigError, Settings

_STRONG_SECRET = "a-strong-generated-secret-of-sufficient-length-0123456789"


def _settings(**overrides: object) -> Settings:
    """Build settings with test-friendly defaults and overrides.

    Args:
        **overrides: Field overrides.

    Returns:
        The settings instance.
    """
    defaults: dict[str, object] = {"database_url": "sqlite+aiosqlite:///:memory:"}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize("environment", ["local", "dev", "test"])
def test_dev_auth_available_in_allowlisted_environments(environment: str) -> None:
    """Dev auth is available only for the closed allowlist."""
    assert _settings(environment=environment).dev_auth_available is True


@pytest.mark.parametrize("environment", ["production", "Production", "prod", "staging", "docker"])
def test_dev_auth_unavailable_outside_allowlist(environment: str) -> None:
    """Non-allowlisted or misspelled environments fail closed with dev auth off."""
    assert _settings(environment=environment).dev_auth_available is False


def test_disabled_flag_overrides_allowlist() -> None:
    """An explicit disable turns dev auth off even in an allowlisted environment."""
    assert _settings(environment="local", dev_auth_enabled=False).dev_auth_available is False


def test_validate_rejects_default_secret_on_shared_dev() -> None:
    """A shared 'dev' environment refuses to start with the insecure default secret."""
    with pytest.raises(InsecureDevAuthConfigError):
        _settings(environment="dev", jwt_secret=INSECURE_DEFAULT_SECRET).validate_runtime()


def test_validate_rejects_short_secret_on_shared_dev() -> None:
    """A shared 'dev' environment refuses to start with a too-short secret."""
    with pytest.raises(InsecureDevAuthConfigError):
        _settings(environment="dev", jwt_secret="short").validate_runtime()


def test_validate_accepts_strong_secret_on_shared_dev() -> None:
    """A shared 'dev' environment starts when given a strong, non-default secret."""
    _settings(environment="dev", jwt_secret=_STRONG_SECRET).validate_runtime()


def test_validate_allows_default_secret_locally() -> None:
    """Local development may use the convenient default secret."""
    _settings(environment="local", jwt_secret=INSECURE_DEFAULT_SECRET).validate_runtime()


def test_validate_ignores_secret_when_dev_auth_unavailable() -> None:
    """Production (dev auth off) does not enforce the dev-auth secret policy."""
    _settings(
        environment="production",
        dev_auth_enabled=True,
        jwt_secret=INSECURE_DEFAULT_SECRET,
    ).validate_runtime()

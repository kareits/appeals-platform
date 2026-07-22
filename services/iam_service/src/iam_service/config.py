"""Runtime configuration for the IAM service.

Settings are loaded from environment variables (prefix ``IAM_``) with local-friendly defaults so
the service runs without external infrastructure during EP-1. Dev/local authentication is available
outside production only (docs/06): production must move to corporate OIDC (ADR-AUTH-OIDC, TASK_06).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# The insecure placeholder signing secret. Tolerated only in strictly local/test environments;
# refused when dev auth is enabled anywhere else (CR-IAM-HIGH-002).
INSECURE_DEFAULT_SECRET = "dev-insecure-secret-change-me-please"

# Closed allowlist of environments where dev/local authentication may be served. Anything else
# (staging, production, a misspelled "Production"/"prod", the compose "docker" default, etc.) fails
# closed with dev auth OFF (CR-IAM-HIGH-002): environment spelling is a security boundary.
DEV_AUTH_ENVIRONMENTS = frozenset({"local", "dev", "test"})

# Environments where the insecure default secret and known dev accounts are acceptable. A shared
# "dev" server is deliberately excluded, so it must supply a strong, non-default secret.
_LOCAL_ONLY_ENVIRONMENTS = frozenset({"local", "test"})

# Minimum length for a signing secret outside the local-only environments.
_MIN_SECRET_LENGTH = 32


class InsecureDevAuthConfigError(RuntimeError):
    """Raised when dev authentication is enabled with unsafe configuration outside local dev."""


class Settings(BaseSettings):
    """Environment-driven settings for the IAM service.

    Attributes:
        environment: The deployment environment name. Dev authentication is available only for the
            closed :data:`DEV_AUTH_ENVIRONMENTS` allowlist (``local``/``dev``/``test``); every other
            value fails closed (CR-IAM-HIGH-002).
        database_url: The SQLAlchemy async database URL.
        dev_auth_enabled: Whether the dev/local login endpoint is enabled. Effective only in an
            allowlisted environment.
        jwt_secret: Symmetric signing secret for dev-issued access tokens. The default is an
            insecure placeholder for local runs only; production uses corporate OIDC (TASK_06) and
            must never rely on this value.
        jwt_algorithm: JWS algorithm for dev tokens. HS256 is used for the temporary symmetric
            scheme; the corporate IdP will use asymmetric signing later.
        jwt_issuer: The ``iss`` claim stamped on dev tokens.
        jwt_audience: The ``aud`` claim stamped on dev tokens; downstream services validate it.
        jwt_ttl_seconds: Lifetime of a dev token, in seconds.
    """

    model_config = SettingsConfigDict(env_prefix="IAM_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./iam_service.db"
    dev_auth_enabled: bool = True
    # TODO(TASK_06B): Replace the dev symmetric secret with corporate OIDC / asymmetric keys and
    # remove the insecure default once secret management and the IdP are in place.
    jwt_secret: str = INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "mfo-iam"
    jwt_audience: str = "mfo-appeals"
    jwt_ttl_seconds: int = 3600

    @property
    def dev_auth_available(self) -> bool:
        """Return whether dev/local login may be served.

        Dev authentication is available only when explicitly enabled and only for the closed
        environment allowlist (docs/06; CR-IAM-HIGH-002). Any non-allowlisted or misspelled
        environment disables it.

        Returns:
            ``True`` when dev login is permitted in this environment.
        """
        return self.dev_auth_enabled and self.environment in DEV_AUTH_ENVIRONMENTS

    def validate_runtime(self) -> None:
        """Fail closed on unsafe dev-auth configuration outside local development.

        When dev auth is available in a shared (non local/test) environment such as ``dev``, refuse
        to start with the insecure default secret or a secret shorter than
        :data:`_MIN_SECRET_LENGTH`, so a shared server cannot run with a repository-known signing
        key (CR-IAM-HIGH-002).

        Raises:
            InsecureDevAuthConfigError: If dev auth is enabled with an unsafe secret in a shared
                environment.
        """
        if not self.dev_auth_available or self.environment in _LOCAL_ONLY_ENVIRONMENTS:
            return
        if self.jwt_secret == INSECURE_DEFAULT_SECRET or len(self.jwt_secret) < _MIN_SECRET_LENGTH:
            raise InsecureDevAuthConfigError(
                f"refusing to start: dev authentication is enabled in environment "
                f"{self.environment!r} with the default or a too-short signing secret. Provide a "
                f"generated IAM_JWT_SECRET of at least {_MIN_SECRET_LENGTH} characters, or disable "
                f"dev auth outside local development."
            )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance.

    Returns:
        The application settings, read from the environment on first access.
    """
    return Settings()

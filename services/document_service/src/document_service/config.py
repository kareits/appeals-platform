"""Runtime configuration for the document service.

Settings are loaded from environment variables (prefix ``DOCUMENT_``) with local-friendly defaults
so the service runs without external infrastructure during EP-2.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

# 25 MiB. A conservative default ceiling on a single upload: the service writes request bodies to
# disk, so an unbounded upload is a storage-exhaustion vector (docs/06 "size limits"). Per-type
# limits and the MIME allowlist arrive with TASK_03A-2.
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class Settings(BaseSettings):
    """Environment-driven settings for the document service.

    Attributes:
        environment: The deployment environment name (for example, ``local`` or ``test``).
        database_url: The SQLAlchemy async database URL used when discrete parts are not supplied.
        db_host: Optional PostgreSQL host. When host/user/name are all set, the connection URL is
            built from these discrete parts with a percent-encoded password, so a secret containing
            URI-reserved characters (``:@/?#``) can never corrupt the URL (CR-BFF-R3-MEDIUM-003).
        db_port: PostgreSQL port used with the discrete parts.
        db_user: PostgreSQL user used with the discrete parts.
        db_password: PostgreSQL password used with the discrete parts (percent-encoded in the URL).
        db_name: PostgreSQL database name used with the discrete parts.
        storage_backend: Identifier of the active storage backend, recorded on every document so a
            later backend can be added without changing document identifiers (ADR-014). Only
            ``local`` is implemented in the MVP.
        storage_root: Filesystem directory holding stored objects. In the compose stack this is a
            persistent volume, so a restart does not lose files.
        max_upload_bytes: Hard ceiling on the **file** bytes of a single upload, enforced while
            streaming to storage; a larger file is rejected with 413 and its partial object is
            discarded. Multipart framing is not counted against it (CR-DOC-MEDIUM-001).
        ticket_base_url: Base URL of the Ticket Service, asked whether a caller may reach an appeal
            (ADR-0012, CR-DOC-HIGH-001). No credentials are configured: the caller's own token is
            forwarded per request.
        ticket_scope_timeout_seconds: Bounded timeout for that decision. A slow decision point must
            fail closed quickly rather than pin document requests open.
        jwt_secret: Symmetric secret used to verify access tokens issued by IAM (dev/local scheme,
            docs/06). The default is an insecure placeholder for local runs and tests only; the
            compose stack and any shared deployment must supply a strong secret matching IAM's.
        jwt_algorithms: Fixed allowlist of accepted JWS algorithms. Pinned to HS256 for the dev
            scheme; the allowlist is the primary defence against ``alg=none``/algorithm confusion.
        jwt_issuer: The expected token ``iss`` claim (IAM's issuer).
        jwt_audience: The expected token ``aud`` claim.
    """

    model_config = SettingsConfigDict(env_prefix="DOCUMENT_", env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "sqlite+aiosqlite:///./document_service.db"
    db_host: str | None = None
    db_port: int = 5432
    db_user: str | None = None
    db_password: str | None = None
    db_name: str | None = None
    storage_backend: str = "local"
    storage_root: Path = Path("./document-storage")
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    ticket_base_url: str = "http://localhost:8000"
    ticket_scope_timeout_seconds: float = 5.0
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
        (CR-BFF-R3-MEDIUM-003). Otherwise ``database_url`` is used as-is (local SQLite/dev).

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

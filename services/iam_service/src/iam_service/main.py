"""FastAPI application factory for the IAM service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mfo_http import CorrelationIdMiddleware, install_problem_detail_handlers
from mfo_observability import configure_logging

from iam_service.api import auth, health, users
from iam_service.config import Settings, get_settings
from iam_service.infrastructure.db import create_engine, create_session_factory
from iam_service.infrastructure.tokens import TokenIssuer


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the IAM-service FastAPI application.

    Wires structured logging, correlation-ID middleware, RFC 7807 error handling, the database
    session factory, the token issuer, and the auth/users/health routers.

    Args:
        settings: Optional settings override; defaults to environment-derived settings.

    Returns:
        The configured FastAPI application.
    """
    resolved = settings or get_settings()
    # Fail closed on unsafe dev-auth configuration before serving any request (CR-IAM-HIGH-002).
    resolved.validate_runtime()
    configure_logging()
    engine = create_engine(resolved.resolved_database_url())
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Dispose of the database engine on shutdown.

        Args:
            app: The FastAPI application.

        Yields:
            Control back to the running application.
        """
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="IAM Service", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_detail_handlers(app)
    app.state.settings = resolved
    app.state.session_factory = session_factory
    app.state.token_issuer = TokenIssuer(
        secret=resolved.jwt_secret,
        algorithm=resolved.jwt_algorithm,
        issuer=resolved.jwt_issuer,
        audience=resolved.jwt_audience,
        ttl_seconds=resolved.jwt_ttl_seconds,
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    return app


app = create_app()
"""Module-level ASGI application instance for servers such as uvicorn."""

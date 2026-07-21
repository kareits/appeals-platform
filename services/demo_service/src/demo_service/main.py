"""FastAPI application factory for the demo service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mfo_http import CorrelationIdMiddleware, install_problem_detail_handlers
from mfo_observability import configure_logging

from demo_service.api import health
from demo_service.config import Settings, get_settings
from demo_service.infrastructure.db import create_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the demo-service FastAPI application.

    Wires structured logging, correlation-ID middleware, RFC 7807 error handling, the database
    session factory, and the health router.

    Args:
        settings: Optional settings override; defaults to environment-derived settings.

    Returns:
        The configured FastAPI application.
    """
    resolved = settings or get_settings()
    configure_logging()
    engine = create_engine(resolved.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Dispose of the database engine on application shutdown.

        Args:
            _: The FastAPI application (unused).

        Yields:
            Control back to the running application.
        """
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Demo Service", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_detail_handlers(app)
    app.state.settings = resolved
    app.state.session_factory = session_factory
    app.include_router(health.router)
    return app


app = create_app()
"""Module-level ASGI application instance for servers such as uvicorn."""

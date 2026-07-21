"""FastAPI application factory for the Process Adapter service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mfo_http import CorrelationIdMiddleware, install_problem_detail_handlers
from mfo_observability import configure_logging

from process_adapter.api import health
from process_adapter.config import Settings, get_settings
from process_adapter.infrastructure.flowable_client import FlowableClient


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the Process Adapter FastAPI application.

    Wires structured logging, correlation-ID middleware, RFC 7807 error handling, the Flowable
    client, and the health router.

    Args:
        settings: Optional settings override; defaults to environment-derived settings.

    Returns:
        The configured FastAPI application.
    """
    resolved = settings or get_settings()
    configure_logging()
    flowable_client = FlowableClient(
        base_url=resolved.flowable_base_url,
        username=resolved.flowable_username,
        password=resolved.flowable_password,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Close the Flowable client on application shutdown.

        Args:
            _: The FastAPI application (unused).

        Yields:
            Control back to the running application.
        """
        try:
            yield
        finally:
            await flowable_client.aclose()

    app = FastAPI(title="Process Adapter", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_detail_handlers(app)
    app.state.settings = resolved
    app.state.flowable_client = flowable_client
    app.include_router(health.router)
    return app


app = create_app()
"""Module-level ASGI application instance for servers such as uvicorn."""

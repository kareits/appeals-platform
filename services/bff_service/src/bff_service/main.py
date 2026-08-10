"""FastAPI application factory for the BFF service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mfo_http import CorrelationIdMiddleware, PlatformHttpClient, install_problem_detail_handlers
from mfo_observability import configure_logging

from bff_service.api import auth, health, reference, tickets
from bff_service.config import Settings, get_settings
from bff_service.infrastructure.db import create_engine, create_session_factory
from bff_service.openapi import committed_openapi


def create_app(
    settings: Settings | None = None,
    *,
    iam_client: PlatformHttpClient | None = None,
    ticket_client: PlatformHttpClient | None = None,
) -> FastAPI:
    """Create and configure the BFF FastAPI application.

    Wires structured logging, correlation-ID middleware, RFC 7807 error handling, the database
    session factory (backing the readiness check), the downstream HTTP clients, and the
    auth/tickets/health routers.

    Args:
        settings: Optional settings override; defaults to environment-derived settings.
        iam_client: Optional pre-built IAM client (used by tests); built from settings otherwise.
        ticket_client: Optional pre-built Ticket client (used by tests); built from settings
            otherwise.

    Returns:
        The configured FastAPI application.
    """
    resolved = settings or get_settings()
    configure_logging()
    engine = create_engine(resolved.resolved_database_url())
    session_factory = create_session_factory(engine)

    # Ownership is tracked per client: a client the caller injected (tests) is theirs to close; a
    # client built here is closed on shutdown. Tracking each independently prevents leaking an
    # internally created client when only one of the two was injected (CR-BFF-MEDIUM-002).
    owns_iam = iam_client is None
    owns_ticket = ticket_client is None
    resolved_iam_client = iam_client or PlatformHttpClient(
        base_url=resolved.iam_base_url, timeout=resolved.http_timeout()
    )
    resolved_ticket_client = ticket_client or PlatformHttpClient(
        base_url=resolved.ticket_base_url, timeout=resolved.http_timeout()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Dispose of the engine and close service-owned HTTP clients on shutdown.

        Args:
            app: The FastAPI application.

        Yields:
            Control back to the running application.
        """
        try:
            yield
        finally:
            if owns_iam:
                await resolved_iam_client.aclose()
            if owns_ticket:
                await resolved_ticket_client.aclose()
            await engine.dispose()

    app = FastAPI(title="BFF Service", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_detail_handlers(app)
    app.state.settings = resolved
    app.state.session_factory = session_factory
    app.state.iam_client = resolved_iam_client
    app.state.ticket_client = resolved_ticket_client
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(tickets.router)
    app.include_router(reference.router)

    def _committed_openapi() -> dict[str, Any]:
        """Serve the committed contract verbatim as the runtime OpenAPI document.

        Returns:
            The committed BFF OpenAPI document (identical runtime/committed schema).
        """
        return committed_openapi(resolved.openapi_contract_path)

    app.openapi = _committed_openapi  # type: ignore[method-assign]
    return app


app = create_app()
"""Module-level ASGI application instance for servers such as uvicorn."""

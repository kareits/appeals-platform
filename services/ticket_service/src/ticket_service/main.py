"""FastAPI application factory for the ticket service."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mfo_http import CorrelationIdMiddleware, install_problem_detail_handlers
from mfo_observability import configure_logging

from ticket_service.api import health, tickets
from ticket_service.config import Settings, get_settings
from ticket_service.infrastructure.auth_tokens import TokenVerifier
from ticket_service.infrastructure.db import create_engine, create_session_factory
from ticket_service.infrastructure.outbox import OutboxRelay, RabbitMqEventPublisher
from ticket_service.infrastructure.registration import RegistrationNumberAllocator

_logger = logging.getLogger(__name__)


async def _run_outbox_relay(relay: OutboxRelay, interval: float) -> None:
    """Continuously publish pending outbox events until cancelled.

    Args:
        relay: The relay that publishes and marks events.
        interval: Seconds to wait between passes.
    """
    while True:
        try:
            await relay.dispatch_pending()
        except Exception:  # noqa: BLE001 - a relay pass must not crash the loop; log and retry.
            _logger.exception("outbox relay pass failed")
        await asyncio.sleep(interval)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the ticket-service FastAPI application.

    Wires structured logging, correlation-ID middleware, RFC 7807 error handling, the database
    session factory, the registration-number allocator, the ticket API, and (optionally) the
    background outbox relay.

    Args:
        settings: Optional settings override; defaults to environment-derived settings.

    Returns:
        The configured FastAPI application.
    """
    resolved = settings or get_settings()
    configure_logging()
    engine = create_engine(resolved.resolved_database_url())
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manage the outbox relay task and dispose of the engine on shutdown.

        Args:
            app: The FastAPI application.

        Yields:
            Control back to the running application.
        """
        relay_task: asyncio.Task[None] | None = None
        publisher: RabbitMqEventPublisher | None = None
        if resolved.outbox_relay_enabled:
            publisher = RabbitMqEventPublisher(resolved.rabbitmq_url, resolved.rabbitmq_exchange)
            relay = OutboxRelay(session_factory, publisher)
            relay_task = asyncio.create_task(
                _run_outbox_relay(relay, resolved.outbox_relay_interval_seconds)
            )
        try:
            yield
        finally:
            if relay_task is not None:
                relay_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await relay_task
            if publisher is not None:
                await publisher.close()
            await engine.dispose()

    app = FastAPI(title="Ticket Service", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_detail_handlers(app)
    app.state.settings = resolved
    app.state.session_factory = session_factory
    app.state.registration_allocator = RegistrationNumberAllocator(
        resolved.registration_number_prefix
    )
    app.state.token_verifier = TokenVerifier(
        secret=resolved.jwt_secret,
        algorithms=resolved.jwt_algorithms,
        issuer=resolved.jwt_issuer,
        audience=resolved.jwt_audience,
    )
    app.include_router(health.router)
    app.include_router(tickets.router)
    return app


app = create_app()
"""Module-level ASGI application instance for servers such as uvicorn."""

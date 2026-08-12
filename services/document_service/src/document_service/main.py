"""FastAPI application factory for the document service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mfo_http import CorrelationIdMiddleware, install_problem_detail_handlers
from mfo_observability import configure_logging

from document_service.api import documents, health
from document_service.config import Settings, get_settings
from document_service.domain.scope import AppealScopeChecker
from document_service.infrastructure.auth_tokens import TokenVerifier
from document_service.infrastructure.db import create_engine, create_session_factory
from document_service.infrastructure.local_storage import BACKEND_NAME, LocalFileStorage
from document_service.infrastructure.ticket_scope import create_scope_checker


def create_app(
    settings: Settings | None = None, *, scope_checker: AppealScopeChecker | None = None
) -> FastAPI:
    """Create and configure the document-service FastAPI application.

    Wires structured logging, correlation-ID middleware, RFC 7807 error handling, the database
    session factory, the file-storage backend, token verification, the appeal-scope decision port,
    and the document API.

    Args:
        settings: Optional settings override; defaults to environment-derived settings.
        scope_checker: Optional appeal-scope port override. Defaults to the Ticket-Service-backed
            adapter; tests substitute a fake so they need no live Ticket Service.

    Returns:
        The configured FastAPI application.

    Raises:
        ValueError: If the configured storage backend is not implemented. Failing at startup is
            deliberate: silently falling back to local storage would write files somewhere the
            operator did not intend (ADR-014 keeps the backend explicit).
    """
    resolved = settings or get_settings()
    configure_logging()
    if resolved.storage_backend != BACKEND_NAME:
        raise ValueError(
            f"unsupported storage backend {resolved.storage_backend!r}; "
            f"only {BACKEND_NAME!r} is implemented (ADR-014)"
        )
    engine = create_engine(resolved.resolved_database_url())
    session_factory = create_session_factory(engine)
    owned_scope_checker = (
        create_scope_checker(resolved.ticket_base_url, resolved.ticket_scope_timeout_seconds)
        if scope_checker is None
        else None
    )
    active_scope_checker = scope_checker or owned_scope_checker

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Dispose of the database engine and the owned HTTP client on shutdown.

        Only a client this factory created is closed; an injected checker belongs to its owner.

        Args:
            app: The FastAPI application.

        Yields:
            Control back to the running application.
        """
        try:
            yield
        finally:
            if owned_scope_checker is not None:
                await owned_scope_checker.aclose()
            await engine.dispose()

    app = FastAPI(title="Document Service", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    install_problem_detail_handlers(app)
    app.state.settings = resolved
    app.state.session_factory = session_factory
    app.state.storage = LocalFileStorage(resolved.storage_root)
    app.state.scope_checker = active_scope_checker
    app.state.token_verifier = TokenVerifier(
        secret=resolved.jwt_secret,
        algorithms=resolved.jwt_algorithms,
        issuer=resolved.jwt_issuer,
        audience=resolved.jwt_audience,
    )
    app.include_router(health.router)
    app.include_router(documents.router)
    return app


app = create_app()
"""Module-level ASGI application instance for servers such as uvicorn."""

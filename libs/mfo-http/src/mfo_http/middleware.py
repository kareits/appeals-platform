"""Correlation-ID ASGI middleware.

Ensures every request has a correlation ID: it reuses an incoming ``X-Correlation-ID`` header when
present, otherwise it generates one. The ID is bound to the observability context (so logs are
correlated) and echoed back on the response.
"""

from __future__ import annotations

from mfo_observability.correlation import (
    CORRELATION_ID_HEADER,
    generate_correlation_id,
    set_correlation_id,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CorrelationIdMiddleware:
    """ASGI middleware that binds a correlation ID to each HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the middleware.

        Args:
            app: The wrapped ASGI application.
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an ASGI event, injecting the correlation ID for HTTP requests.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        correlation_id = self._read_header(scope) or generate_correlation_id()
        set_correlation_id(correlation_id)

        async def send_with_header(message: Message) -> None:
            """Append the correlation-ID header to the response start event.

            Args:
                message: The outgoing ASGI message.
            """
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append(
                    (CORRELATION_ID_HEADER.encode("latin-1"), correlation_id.encode("latin-1"))
                )
            await send(message)

        await self._app(scope, receive, send_with_header)

    @staticmethod
    def _read_header(scope: Scope) -> str | None:
        """Extract the correlation-ID header from an ASGI scope.

        Args:
            scope: The ASGI connection scope.

        Returns:
            The header value, or ``None`` when it is absent.
        """
        target = CORRELATION_ID_HEADER.lower().encode("latin-1")
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        for name, value in headers:
            if name.lower() == target:
                return value.decode("latin-1")
        return None

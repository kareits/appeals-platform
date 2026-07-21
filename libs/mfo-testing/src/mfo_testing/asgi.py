"""In-process ASGI test-client factory.

Builds an ``httpx.AsyncClient`` wired to an ASGI application via ``ASGITransport``, so API tests
run in-process without binding a network port.
"""

from __future__ import annotations

import httpx


def create_asgi_client(app: object, base_url: str = "http://testserver") -> httpx.AsyncClient:
    """Create an async HTTP client bound to an ASGI application.

    Args:
        app: The ASGI application to route requests to.
        base_url: The base URL used for request resolution.

    Returns:
        An ``httpx.AsyncClient`` that dispatches requests directly to ``app``.
    """
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url=base_url)

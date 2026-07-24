"""Shared pytest fixtures for BFF-service tests.

Tests wire the gateway against fake IAM and Ticket services implemented with
``httpx.MockTransport``, so BFF-to-IAM/Ticket integration runs in-process without real services. The
reusable fake
handlers and type aliases live in ``bff_fakes`` (a uniquely named module) rather than here, so test
modules can import them directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest_asyncio
from bff_fakes import IAM_BASE_URL, TICKET_BASE_URL, ClientFactory, Handler, reject_all
from bff_service.config import Settings
from bff_service.main import create_app
from mfo_http import PlatformHttpClient
from mfo_testing import create_asgi_client


@pytest_asyncio.fixture
async def build_client() -> AsyncIterator[ClientFactory]:
    """Yield a factory that builds a gateway client over fake IAM and Ticket services.

    The factory accepts optional ``iam_handler`` and ``ticket_handler`` mock-transport callables and
    returns an entered ``httpx.AsyncClient`` bound to the gateway. All created clients are closed
    when the fixture tears down.

    Yields:
        A callable returning an async client bound to a freshly wired gateway.
    """
    cleanups: list[Callable[[], Awaitable[None]]] = []

    async def _build(
        iam_handler: Handler | None = None, ticket_handler: Handler | None = None
    ) -> httpx.AsyncClient:
        """Wire a gateway with the given fake upstreams and return an entered client.

        Args:
            iam_handler: Optional fake IAM handler; rejects all by default.
            ticket_handler: Optional fake Ticket handler; rejects all by default.

        Returns:
            An entered async client bound to the gateway.
        """
        settings = Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            iam_base_url=IAM_BASE_URL,
            ticket_base_url=TICKET_BASE_URL,
        )
        iam_client = PlatformHttpClient(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(iam_handler or reject_all), base_url=IAM_BASE_URL
            )
        )
        ticket_client = PlatformHttpClient(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(ticket_handler or reject_all),
                base_url=TICKET_BASE_URL,
            )
        )
        app = create_app(settings, iam_client=iam_client, ticket_client=ticket_client)
        client = create_asgi_client(app)
        await client.__aenter__()

        async def _close() -> None:
            """Close the client and its upstream clients."""
            await client.__aexit__(None, None, None)
            await iam_client.aclose()
            await ticket_client.aclose()

        cleanups.append(_close)
        return client

    yield _build

    for close in cleanups:
        await close()

"""Lifecycle and timeout-configuration tests for the BFF service (CR-BFF-MEDIUM-002)."""

from __future__ import annotations

import httpx
import pytest
from bff_service.config import Settings
from bff_service.main import create_app
from mfo_http import PlatformHttpClient
from pydantic import ValidationError


def test_zero_timeout_is_rejected() -> None:
    """A non-positive timeout fails configuration validation (protection cannot be disabled)."""
    with pytest.raises(ValidationError):
        Settings(http_read_timeout_seconds=0)


def test_negative_timeout_is_rejected() -> None:
    """A negative timeout fails configuration validation."""
    with pytest.raises(ValidationError):
        Settings(http_connect_timeout_seconds=-1)


def test_infinite_timeout_is_rejected() -> None:
    """A non-finite timeout fails configuration validation."""
    with pytest.raises(ValidationError):
        Settings(workspace_deadline_seconds=float("inf"))


def _dummy_client() -> PlatformHttpClient:
    """Build a mock-transport HTTP client that answers everything with 200.

    Returns:
        A platform HTTP client over a mock transport.
    """
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    return PlatformHttpClient(client=httpx.AsyncClient(transport=transport, base_url="http://x"))


async def test_partial_client_injection_closes_internal_client() -> None:
    """With only one client injected, the internally created client is still closed at shutdown."""
    injected_iam = _dummy_client()
    app = create_app(
        Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"),
        iam_client=injected_iam,
    )
    internal_ticket: PlatformHttpClient = app.state.ticket_client

    async with app.router.lifespan_context(app):
        pass

    # The internally created ticket client is closed; the injected IAM client is left to its owner.
    assert internal_ticket._client.is_closed
    assert not injected_iam._client.is_closed
    await injected_iam.aclose()

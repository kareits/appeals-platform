"""Health-endpoint tests for the BFF service."""

from __future__ import annotations

from bff_fakes import ClientFactory


async def test_live_reports_alive(build_client: ClientFactory) -> None:
    """The liveness endpoint reports the process is running."""
    client = await build_client()
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_ready_reports_healthy(build_client: ClientFactory) -> None:
    """The readiness endpoint reports healthy when the gateway database is reachable."""
    client = await build_client()
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "healthy"

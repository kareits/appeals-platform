"""Tests for the demo-service health endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness_returns_alive(client: AsyncClient) -> None:
    """The liveness endpoint reports that the process is alive and echoes a correlation ID."""
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert "X-Correlation-ID" in response.headers


async def test_readiness_reports_healthy(client: AsyncClient) -> None:
    """The readiness endpoint reports healthy when the database is reachable."""
    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "healthy"

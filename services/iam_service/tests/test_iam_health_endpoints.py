"""Tests for the IAM-service health endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_live_returns_alive(client: AsyncClient) -> None:
    """The liveness endpoint reports the process is alive."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_ready_reports_database_healthy(client: AsyncClient) -> None:
    """The readiness endpoint reports a healthy database."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"]["database"] == "healthy"
    # Readiness is schema-aware: it verifies a core IAM table exists (CR-IAM-HIGH-001).
    assert body["checks"]["schema"] == "healthy"

"""Health-check HTTP endpoints for the Process Adapter."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from mfo_observability import HealthStatus, run_health_checks

from process_adapter.application.health import FlowableHealthCheck

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Report process liveness.

    Returns:
        A payload indicating the process is running.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Report readiness by checking Flowable connectivity.

    Args:
        request: The incoming request, used to access the app's Flowable client.

    Returns:
        A JSON response with the aggregate status and per-check results.
    """
    client = request.app.state.flowable_client
    report = await run_health_checks([FlowableHealthCheck(client)])
    status_code = 200 if report.status is HealthStatus.HEALTHY else 503
    body = {
        "status": report.status.value,
        "checks": {name: status.value for name, status in report.checks.items()},
    }
    return JSONResponse(body, status_code=status_code)

"""Health-check HTTP endpoints for the BFF service."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from mfo_observability import HealthStatus, run_health_checks

from bff_service.application.health import DatabaseHealthCheck

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
    """Report readiness by checking the gateway's own database connectivity.

    Downstream (IAM/Ticket) reachability is deliberately excluded: a downstream outage degrades a
    workspace read but must not mark the gateway unready.

    Args:
        request: The incoming request, used to access the app's session factory.

    Returns:
        A JSON response with the aggregate status and per-check results.
    """
    session_factory = request.app.state.session_factory
    report = await run_health_checks([DatabaseHealthCheck(session_factory)])
    status_code = 200 if report.status is HealthStatus.HEALTHY else 503
    body = {
        "status": report.status.value,
        "checks": {name: status.value for name, status in report.checks.items()},
    }
    return JSONResponse(body, status_code=status_code)

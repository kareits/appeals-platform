"""Health-check HTTP endpoints for the document service."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from mfo_observability import HealthStatus, run_health_checks

from document_service.application.health import DatabaseHealthCheck, StorageHealthCheck

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
    """Report readiness by checking downstream dependencies.

    Runs the database connectivity check and the storage-root write probe, returning HTTP 200 when
    both are healthy or HTTP 503 otherwise. Storage is part of readiness because a service with an
    unmounted or read-only volume can still answer metadata queries while every upload fails.

    Args:
        request: The incoming request, used to access the app's session factory and storage root.

    Returns:
        A JSON response with the aggregate status and per-check results.
    """
    session_factory = request.app.state.session_factory
    storage_root = request.app.state.storage.root
    report = await run_health_checks(
        [DatabaseHealthCheck(session_factory), StorageHealthCheck(storage_root)]
    )
    status_code = 200 if report.status is HealthStatus.HEALTHY else 503
    body = {
        "status": report.status.value,
        "checks": {name: status.value for name, status in report.checks.items()},
    }
    return JSONResponse(body, status_code=status_code)

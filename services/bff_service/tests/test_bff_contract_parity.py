"""Conformance tests between the running BFF app and the committed OpenAPI contract.

The gateway serves the committed contract verbatim as its runtime OpenAPI (``app.openapi``), so the
runtime and committed documents are identical by construction — every path, parameter, request and
response body, response code, media type, header and RFC 7807 shape matches, with no forwarded-body
or media-type drift (CR-BFF-R4-MEDIUM-001). These tests assert that identity, that the served
document is valid OpenAPI, and that the app's actual routes correspond exactly to the contract's
operations (no undocumented route and no documented-but-missing operation).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import yaml
from bff_service.config import Settings
from bff_service.main import create_app
from fastapi.routing import APIRoute
from openapi_spec_validator import validate

_SPEC_PATH = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "bff-service.v1.yaml"
_HTTP_METHODS = {"get", "post", "patch", "put", "delete"}


def _committed_spec() -> dict[str, Any]:
    """Load the committed OpenAPI document.

    Returns:
        The parsed specification.
    """
    return cast(dict[str, Any], yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8")))


def _app() -> Any:
    """Build a BFF app instance for introspection.

    Returns:
        The FastAPI application.
    """
    return create_app(Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"))


def _server_base(spec: dict[str, Any]) -> str:
    """Return the server base path of a spec (empty when none).

    Args:
        spec: An OpenAPI document.

    Returns:
        The first server URL without a trailing slash.
    """
    servers = spec.get("servers") or [{"url": ""}]
    return str(servers[0]["url"]).rstrip("/")


def _contract_operations(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """Collect ``(method, full path)`` pairs documented in the contract.

    Args:
        spec: An OpenAPI document.

    Returns:
        The set of documented method/path pairs, each path made absolute via the server base.
    """
    base = _server_base(spec)
    ops: set[tuple[str, str]] = set()
    for path, path_item in spec["paths"].items():
        for method in path_item:
            if method in _HTTP_METHODS:
                ops.add((method, f"{base}{path}"))
    return ops


def _iter_api_routes(routes: list[Any]) -> Iterator[APIRoute]:
    """Yield every :class:`APIRoute`, recursing into included/mounted routers.

    Args:
        routes: A list of Starlette/FastAPI routes.

    Yields:
        Each API route found at any nesting depth.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        # FastAPI include_router wraps routes; the concrete APIRoutes live on the wrapped router
        # (``original_router``) or a nested ``routes`` list depending on the version.
        nested = getattr(route, "routes", None)
        if nested:
            yield from _iter_api_routes(nested)
        original = getattr(route, "original_router", None)
        if original is not None and getattr(original, "routes", None):
            yield from _iter_api_routes(original.routes)


def _route_operations(app: Any) -> set[tuple[str, str]]:
    """Collect ``(method, path)`` pairs of the app's real API routes (under ``/api/v1``).

    Args:
        app: The FastAPI application.

    Returns:
        The set of method/path pairs the app actually serves under ``/api/v1``.
    """
    ops: set[tuple[str, str]] = set()
    for route in _iter_api_routes(app.routes):
        if not route.path.startswith("/api/v1"):
            continue
        for method in route.methods or set():
            if method.lower() in _HTTP_METHODS:
                ops.add((method.lower(), route.path))
    return ops


def test_runtime_openapi_is_the_committed_contract() -> None:
    """The runtime OpenAPI document is exactly the committed contract (served verbatim)."""
    assert _app().openapi() == _committed_spec()


def test_served_contract_is_valid_openapi() -> None:
    """The served runtime document is syntactically valid OpenAPI 3.1."""
    validate(_app().openapi())


def test_routes_correspond_to_contract_operations() -> None:
    """Every app route is documented and every documented operation has a route (exact set)."""
    assert _route_operations(_app()) == _contract_operations(_committed_spec())


async def test_openapi_json_http_endpoint_serves_committed_contract() -> None:
    """The real ``GET /openapi.json`` HTTP endpoint returns exactly the committed contract."""
    from mfo_testing import create_asgi_client

    async with create_asgi_client(_app()) as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == _committed_spec()

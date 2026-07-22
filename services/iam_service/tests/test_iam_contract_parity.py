"""Parity tests between the running IAM app and the committed OpenAPI contract.

The runtime FastAPI schema and the hand-written contract must not drift. These tests compare the
full set of operations (method + normalized path), that every protected operation actually carries a
security requirement at runtime, and that response bodies advertise the same required fields as the
contract. Path-parameter identifiers are normalized because their spelling is a local implementation
detail, not part of the wire contract (CR-IAM-MEDIUM-001).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml
from iam_service.config import Settings
from iam_service.main import create_app

_SPEC_PATH = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "iam-service.v1.yaml"
_HTTP_METHODS = {"get", "post", "patch", "put", "delete"}
_PARAM = re.compile(r"\{[^}]+\}")
# Operations that require a bearer token (everything except the public dev login).
_PROTECTED_OPERATIONS = {"getCurrentSubject", "createUser", "getUser", "assignRole", "revokeRole"}
_RESPONSE_SCHEMAS = ("TokenResponse", "SubjectResponse", "UserResponse")


def _committed_spec() -> dict[str, Any]:
    """Load the committed OpenAPI document.

    Returns:
        The parsed specification.
    """
    return cast(dict[str, Any], yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8")))


def _runtime_spec() -> dict[str, Any]:
    """Generate the OpenAPI document from the running application.

    Returns:
        The application's generated specification.
    """
    app = create_app(Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"))
    spec: dict[str, Any] = app.openapi()
    return spec


def _normalize(path: str) -> str:
    """Normalize a templated path by collapsing parameter names.

    Args:
        path: An OpenAPI path template.

    Returns:
        The path with every ``{param}`` replaced by ``{}``.
    """
    return _PARAM.sub("{}", path)


def _base(spec: dict[str, Any]) -> str:
    """Return the server base path of a spec (empty when none).

    Args:
        spec: An OpenAPI document.

    Returns:
        The first server URL without a trailing slash.
    """
    servers = spec.get("servers") or [{"url": ""}]
    return str(servers[0]["url"]).rstrip("/")


def _operations(spec: dict[str, Any], *, exclude_health: bool = False) -> set[tuple[str, str]]:
    """Collect ``(method, normalized full path)`` pairs from a spec.

    Args:
        spec: An OpenAPI document.
        exclude_health: When set, skip operations mounted under ``/health``.

    Returns:
        The set of method/path pairs, each path made absolute via the server base and normalized.
    """
    base = _base(spec)
    ops: set[tuple[str, str]] = set()
    for path, path_item in spec["paths"].items():
        if exclude_health and path.startswith("/health"):
            continue
        full = _normalize(f"{base}{path}")
        for method in path_item:
            if method in _HTTP_METHODS:
                ops.add((method, full))
    return ops


def _operations_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index operations by their operationId.

    Args:
        spec: An OpenAPI document.

    Returns:
        A mapping from operationId to the operation object.
    """
    return {
        operation["operationId"]: operation
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in _HTTP_METHODS and "operationId" in operation
    }


def test_runtime_paths_and_methods_match_contract() -> None:
    """The runtime exposes exactly the contract's method/path pairs (health aside)."""
    assert _operations(_committed_spec()) == _operations(_runtime_spec(), exclude_health=True)


def _security_refs(operation: dict[str, Any]) -> set[frozenset[str]]:
    """Return an operation's security requirement as a set of scheme-name sets.

    Args:
        operation: An OpenAPI operation object.

    Returns:
        Each alternative requirement rendered as the frozenset of scheme names it references.
    """
    return {frozenset(requirement) for requirement in operation.get("security", [])}


def test_protected_operations_reference_the_same_security_scheme() -> None:
    """Each protected operation references the exact same security scheme in both documents.

    Comparing only presence would miss a scheme-name mismatch (for example runtime ``HTTPBearer``
    versus committed ``bearerAuth``); this asserts the exact references and that the named scheme is
    defined identically in both documents (CR-IAM-MEDIUM-001).
    """
    committed_spec = _committed_spec()
    runtime_spec = _runtime_spec()
    committed = _operations_by_id(committed_spec)
    runtime = _operations_by_id(runtime_spec)

    for operation_id in _PROTECTED_OPERATIONS:
        refs = _security_refs(committed[operation_id])
        assert refs == {frozenset({"bearerAuth"})}, operation_id
        assert _security_refs(runtime[operation_id]) == refs, operation_id

    # The public login must not require authentication in either document.
    assert not committed["devLogin"].get("security")
    assert not runtime["devLogin"].get("security")

    # The referenced scheme must be defined as an identical bearer/JWT scheme in both documents.
    committed_scheme = committed_spec["components"]["securitySchemes"]["bearerAuth"]
    runtime_scheme = runtime_spec["components"]["securitySchemes"]["bearerAuth"]
    for field in ("type", "scheme", "bearerFormat"):
        assert committed_scheme.get(field) == runtime_scheme.get(field), field


def test_response_required_fields_match_contract() -> None:
    """Response schemas advertise the same required fields at runtime as in the contract."""
    committed = _committed_spec()["components"]["schemas"]
    runtime = _runtime_spec()["components"]["schemas"]
    for name in _RESPONSE_SCHEMAS:
        assert set(committed[name].get("required", [])) == set(runtime[name].get("required", [])), (
            name
        )


def test_request_bodies_forbid_unknown_properties() -> None:
    """Every contract request body advertises additionalProperties: false (strict input)."""
    schemas = _committed_spec()["components"]["schemas"]
    for name in ("LoginRequest", "CreateUserRequest", "AssignRoleRequest"):
        assert schemas[name]["additionalProperties"] is False, name

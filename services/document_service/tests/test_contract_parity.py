"""Parity tests between the runtime OpenAPI document and the committed contract.

Contract-first means the committed ``contracts/openapi/document-service.v1.yaml`` is authoritative
(docs/05). FastAPI generates its own document from the route signatures, so the two can drift
silently; these tests compare them operation by operation — paths and methods, security, the exact
set of declared status codes, and the canonical form of every request/response schema — so a change
to either side fails here rather than in an integration weeks later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from document_service.config import Settings
from document_service.main import create_app

_CONTRACT = (
    Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "document-service.v1.yaml"
)
_HTTP_METHODS = {"get", "post", "patch", "put", "delete"}
# The contract documents the versioned API only; health endpoints are operational, not a contract.
_RUNTIME_PREFIX = "/api/v1"


def _runtime_openapi(tmp_path: Path) -> dict[str, Any]:
    """Build the runtime OpenAPI document from the FastAPI app.

    Args:
        tmp_path: Pytest-provided temporary directory used for the throwaway settings.

    Returns:
        The generated OpenAPI document.
    """
    app = create_app(
        Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            storage_root=tmp_path / "storage",
        )
    )
    return dict(app.openapi())


def _contract() -> dict[str, Any]:
    """Load the committed OpenAPI contract.

    Returns:
        The parsed contract document.
    """
    return cast(dict[str, Any], yaml.safe_load(_CONTRACT.read_text(encoding="utf-8")))


def _operations(spec: dict[str, Any], *, strip_prefix: str = "") -> dict[str, dict[str, Any]]:
    """Index a spec's API operations by operationId, keeping their path, method, and parameters.

    Parameters declared once for a path item apply to every operation under it, so they are
    merged into each operation here; comparing only the operation-level list would miss a
    path-level parameter entirely (CR-DOC-MEDIUM-003).

    Args:
        spec: An OpenAPI document.
        strip_prefix: Path prefix to remove (the runtime mounts the contract's server base path).

    Returns:
        A mapping of operationId to a dict with ``path``, ``method``, the operation object, and its
        merged parameter list.
    """
    indexed: dict[str, dict[str, Any]] = {}
    for path, path_item in spec["paths"].items():
        if strip_prefix:
            if not path.startswith(strip_prefix):
                continue
            path = path[len(strip_prefix) :]
        shared_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS:
                continue
            indexed[operation["operationId"]] = {
                "path": path,
                "method": method,
                "operation": operation,
                "parameters": [*shared_parameters, *operation.get("parameters", [])],
            }
    return indexed


def _resolve_component(node: dict[str, Any], spec: dict[str, Any], section: str) -> dict[str, Any]:
    """Resolve a ``$ref`` into one of the document's component sections.

    Args:
        node: A node that may be a ``$ref``.
        spec: The full OpenAPI document.
        section: The component section to resolve into (for example ``parameters``).

    Returns:
        The resolved node.
    """
    while "$ref" in node:
        name = node["$ref"].split("/")[-1]
        node = cast(dict[str, Any], spec["components"][section][name])
    return node


def _canonical_parameters(
    entry: dict[str, Any], spec: dict[str, Any]
) -> dict[tuple[str, str], Any]:
    """Reduce an operation's parameters to a comparable mapping keyed by name and location.

    Args:
        entry: An indexed operation (with its merged parameter list).
        spec: The document the operation came from, for ``$ref`` resolution.

    Returns:
        A mapping of ``(name, in)`` to the parameter's required flag and canonical schema.
    """
    components = _components(spec)
    canonical: dict[tuple[str, str], Any] = {}
    for raw in entry["parameters"]:
        parameter = _resolve_component(raw, spec, "parameters")
        canonical[(parameter["name"], parameter["in"])] = {
            "required": bool(parameter.get("required", False)),
            "schema": _canonical(parameter.get("schema", {}), components),
        }
    return canonical


def _canonical_headers(response: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Reduce a response's declared headers to a comparable mapping.

    Args:
        response: A response object (already dereferenced).
        spec: The document the response came from, for ``$ref`` resolution.

    Returns:
        A mapping of header name to its canonical schema.
    """
    components = _components(spec)
    return {
        name: _canonical(_resolve_component(header, spec, "headers").get("schema", {}), components)
        for name, header in response.get("headers", {}).items()
    }


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Resolve a top-level ``$ref`` against the component schemas.

    Args:
        schema: A schema that may be a ``$ref``.
        components: The component-schema map.

    Returns:
        The resolved schema.
    """
    while "$ref" in schema:
        schema = cast(dict[str, Any], components[schema["$ref"].split("/")[-1]])
    return schema


def _canonical(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Reduce a schema to a canonical, comparable form.

    Resolves ``$ref``, normalizes nullable unions (runtime ``anyOf: [X, null]`` versus contract
    ``type: [X, "null"]``) to a base type plus a ``nullable`` flag, and recurses into properties and
    array items. Titles, descriptions, defaults, and examples are ignored: they are documentation,
    not wire behavior.

    Args:
        schema: The schema to canonicalize.
        components: The component-schema map for ``$ref`` resolution.

    Returns:
        The canonical representation.
    """
    schema = _resolve(schema, components)
    nullable = False

    variants = schema.get("anyOf") or schema.get("oneOf")
    if variants:
        resolved = [_resolve(variant, components) for variant in variants]
        non_null = [variant for variant in resolved if variant.get("type") != "null"]
        nullable = len(non_null) != len(resolved)
        if len(non_null) == 1:
            schema = non_null[0]
            schema = _resolve(schema, components)
        else:  # pragma: no cover - the document uses no multi-variant unions.
            return {"anyOf": [_canonical(variant, components) for variant in non_null]}

    declared_type = schema.get("type")
    if isinstance(declared_type, list):
        nullable = nullable or "null" in declared_type
        remaining = [item for item in declared_type if item != "null"]
        declared_type = remaining[0] if len(remaining) == 1 else remaining

    canonical: dict[str, Any] = {"type": declared_type, "nullable": nullable}
    for keyword in (
        "format",
        "contentMediaType",
        "enum",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
    ):
        if keyword in schema:
            canonical[keyword] = schema[keyword]
    if "additionalProperties" in schema:
        canonical["additionalProperties"] = schema["additionalProperties"]
    if "required" in schema:
        canonical["required"] = sorted(schema["required"])
    if "properties" in schema:
        canonical["properties"] = {
            name: _canonical(value, components)
            for name, value in sorted(schema["properties"].items())
        }
    if "items" in schema:
        canonical["items"] = _canonical(schema["items"], components)
    return canonical


def _components(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a spec's component schemas.

    Args:
        spec: An OpenAPI document.

    Returns:
        The component-schema map.
    """
    return cast(dict[str, Any], spec.get("components", {}).get("schemas", {}))


def _body_schema(operation: dict[str, Any], media_type: str) -> dict[str, Any] | None:
    """Return an operation's request-body schema for a media type, if declared.

    Args:
        operation: The operation object.
        media_type: The media type to look up.

    Returns:
        The schema, or ``None`` when the operation declares no such body.
    """
    content = operation.get("requestBody", {}).get("content", {})
    schema = content.get(media_type, {}).get("schema")
    return cast(dict[str, Any] | None, schema)


def _response_schema(operation: dict[str, Any], status: str, media_type: str) -> dict[str, Any]:
    """Return an operation's response schema for a status code and media type.

    Args:
        operation: The operation object.
        status: The status code as a string key.
        media_type: The media type to look up.

    Returns:
        The schema.
    """
    return cast(dict[str, Any], operation["responses"][status]["content"][media_type]["schema"])


def test_runtime_operations_match_the_contract(tmp_path: Path) -> None:
    """Every contract operation exists at the same path and method at runtime, and none extra."""
    runtime = _operations(_runtime_openapi(tmp_path), strip_prefix=_RUNTIME_PREFIX)
    contract = _operations(_contract())

    assert runtime.keys() == contract.keys()
    for operation_id, expected in contract.items():
        assert (runtime[operation_id]["path"], runtime[operation_id]["method"]) == (
            expected["path"],
            expected["method"],
        ), operation_id


def test_every_operation_requires_the_same_bearer_scheme(tmp_path: Path) -> None:
    """Runtime and contract protect all operations with an identically defined ``bearerAuth``."""
    runtime_spec = _runtime_openapi(tmp_path)
    contract_spec = _contract()

    runtime_scheme = runtime_spec["components"]["securitySchemes"]["bearerAuth"]
    contract_scheme = contract_spec["components"]["securitySchemes"]["bearerAuth"]
    assert (runtime_scheme["type"], runtime_scheme["scheme"], runtime_scheme["bearerFormat"]) == (
        contract_scheme["type"],
        contract_scheme["scheme"],
        contract_scheme["bearerFormat"],
    )

    # The contract applies security globally; the runtime declares it per operation.
    assert contract_spec["security"] == [{"bearerAuth": []}]
    for operation_id, entry in _operations(runtime_spec, strip_prefix=_RUNTIME_PREFIX).items():
        assert entry["operation"]["security"] == [{"bearerAuth": []}], operation_id


def test_declared_status_codes_match(tmp_path: Path) -> None:
    """Each operation declares exactly the same response codes on both sides."""
    runtime = _operations(_runtime_openapi(tmp_path), strip_prefix=_RUNTIME_PREFIX)
    contract = _operations(_contract())

    for operation_id, expected in contract.items():
        assert set(runtime[operation_id]["operation"]["responses"]) == set(
            expected["operation"]["responses"]
        ), operation_id


def test_operation_parameters_match(tmp_path: Path) -> None:
    """Every operation declares the same path, query, and header parameters on both sides.

    Regression guard for CR-DOC-MEDIUM-003: the runtime document previously omitted the committed
    ``X-Correlation-ID`` request parameter and advertised an undocumented ``Content-Length`` header
    parameter on upload, while the parity suite passed because parameters were never inspected.
    """
    runtime_spec = _runtime_openapi(tmp_path)
    contract_spec = _contract()
    runtime = _operations(runtime_spec, strip_prefix=_RUNTIME_PREFIX)
    contract = _operations(contract_spec)

    for operation_id, expected in contract.items():
        assert _canonical_parameters(runtime[operation_id], runtime_spec) == _canonical_parameters(
            expected, contract_spec
        ), operation_id


def test_response_headers_match(tmp_path: Path) -> None:
    """Every declared response header exists on both sides with the same schema.

    Also part of CR-DOC-MEDIUM-003: the contract advertised correlation, attachment, and
    nosniff headers that the generated runtime document never declared.
    """
    runtime_spec = _runtime_openapi(tmp_path)
    contract_spec = _contract()
    runtime = _operations(runtime_spec, strip_prefix=_RUNTIME_PREFIX)
    contract = _operations(contract_spec)

    for operation_id, expected in contract.items():
        runtime_responses = runtime[operation_id]["operation"]["responses"]
        for status, contract_response in expected["operation"]["responses"].items():
            resolved = _resolve_component(contract_response, contract_spec, "responses")
            assert _canonical_headers(
                runtime_responses[status], runtime_spec
            ) == _canonical_headers(resolved, contract_spec), (operation_id, status)


def test_parity_detects_a_missing_parameter(tmp_path: Path) -> None:
    """The parameter comparison actually fails when a surface drifts.

    A parity test that never fails is worse than none, so the comparison is exercised against a
    mutated document: dropping the correlation-ID parameter from one side must be detected.
    """
    contract_spec = _contract()
    mutated = _operations(contract_spec)["getDocument"]
    intact = _canonical_parameters(mutated, contract_spec)
    without_header = {
        "path": mutated["path"],
        "method": mutated["method"],
        "operation": mutated["operation"],
        "parameters": [
            parameter
            for parameter in mutated["parameters"]
            if parameter.get("$ref", "").split("/")[-1] != "CorrelationId"
        ],
    }

    assert _canonical_parameters(without_header, contract_spec) != intact


def test_parity_detects_a_missing_response_header(tmp_path: Path) -> None:
    """The response-header comparison actually fails when a header disappears."""
    contract_spec = _contract()
    download = _operations(contract_spec)["downloadDocument"]["operation"]
    intact = _canonical_headers(download["responses"]["200"], contract_spec)
    stripped = dict(download["responses"]["200"])
    stripped["headers"] = {
        name: value
        for name, value in stripped["headers"].items()
        if name != "X-Content-Type-Options"
    }

    assert _canonical_headers(stripped, contract_spec) != intact


def test_link_request_body_matches(tmp_path: Path) -> None:
    """The one JSON request body is field-for-field identical, including strictness."""
    runtime_spec = _runtime_openapi(tmp_path)
    contract_spec = _contract()
    runtime_op = _operations(runtime_spec, strip_prefix=_RUNTIME_PREFIX)["linkDocument"][
        "operation"
    ]
    contract_op = _operations(contract_spec)["linkDocument"]["operation"]

    runtime_body = _body_schema(runtime_op, "application/json")
    contract_body = _body_schema(contract_op, "application/json")
    assert runtime_body is not None
    assert contract_body is not None

    canonical_runtime = _canonical(runtime_body, _components(runtime_spec))
    canonical_contract = _canonical(contract_body, _components(contract_spec))
    assert canonical_runtime["required"] == canonical_contract["required"]
    assert canonical_runtime["properties"] == canonical_contract["properties"]
    # Unknown properties are rejected on both sides.
    assert canonical_runtime.get("additionalProperties") is False
    assert canonical_contract.get("additionalProperties") is False


def test_upload_multipart_fields_match(tmp_path: Path) -> None:
    """The multipart upload declares the same fields, required set, and binary part."""
    runtime_spec = _runtime_openapi(tmp_path)
    contract_spec = _contract()
    runtime_op = _operations(runtime_spec, strip_prefix=_RUNTIME_PREFIX)["uploadDocument"][
        "operation"
    ]
    contract_op = _operations(contract_spec)["uploadDocument"]["operation"]

    runtime_body = _body_schema(runtime_op, "multipart/form-data")
    contract_body = _body_schema(contract_op, "multipart/form-data")
    assert runtime_body is not None
    assert contract_body is not None

    canonical_runtime = _canonical(runtime_body, _components(runtime_spec))
    canonical_contract = _canonical(contract_body, _components(contract_spec))
    assert canonical_runtime["properties"].keys() == canonical_contract["properties"].keys()
    assert canonical_runtime["required"] == canonical_contract["required"] == ["file"]
    for schema in (canonical_runtime, canonical_contract):
        assert schema["properties"]["file"]["contentMediaType"] == "application/octet-stream"
    for field in ("ticketId", "messageId"):
        assert canonical_runtime["properties"][field]["format"] == "uuid"
        assert canonical_contract["properties"][field]["format"] == "uuid"


@pytest.mark.parametrize(
    ("operation_id", "status"),
    [
        ("uploadDocument", "201"),
        ("getDocument", "200"),
        ("listTicketDocuments", "200"),
        ("linkDocument", "200"),
    ],
)
def test_success_response_schemas_match(tmp_path: Path, operation_id: str, status: str) -> None:
    """Every JSON success payload is structurally identical on both sides."""
    runtime_spec = _runtime_openapi(tmp_path)
    contract_spec = _contract()
    runtime_op = _operations(runtime_spec, strip_prefix=_RUNTIME_PREFIX)[operation_id]["operation"]
    contract_op = _operations(contract_spec)[operation_id]["operation"]

    canonical_runtime = _canonical(
        _response_schema(runtime_op, status, "application/json"), _components(runtime_spec)
    )
    canonical_contract = _canonical(
        _response_schema(contract_op, status, "application/json"), _components(contract_spec)
    )

    assert canonical_runtime == canonical_contract


def test_download_response_is_binary_on_both_sides(tmp_path: Path) -> None:
    """The download operation streams octets, never a browser-renderable media type."""
    runtime_op = _operations(_runtime_openapi(tmp_path), strip_prefix=_RUNTIME_PREFIX)[
        "downloadDocument"
    ]["operation"]
    contract_op = _operations(_contract())["downloadDocument"]["operation"]

    assert set(runtime_op["responses"]["200"]["content"]) == {"application/octet-stream"}
    assert set(contract_op["responses"]["200"]["content"]) == {"application/octet-stream"}


def test_error_responses_use_problem_json(tmp_path: Path) -> None:
    """Every declared error response carries an RFC 7807 body on both sides."""
    runtime = _operations(_runtime_openapi(tmp_path), strip_prefix=_RUNTIME_PREFIX)
    contract_spec = _contract()
    contract = _operations(contract_spec)

    for operation_id, entry in contract.items():
        for status, response in entry["operation"]["responses"].items():
            if not status.startswith(("4", "5")):
                continue
            resolved = response
            if "$ref" in resolved:
                name = resolved["$ref"].split("/")[-1]
                resolved = contract_spec["components"]["responses"][name]
            assert set(resolved["content"]) == {"application/problem+json"}, (
                operation_id,
                status,
            )
            runtime_response = runtime[operation_id]["operation"]["responses"][status]
            assert set(runtime_response["content"]) == {"application/problem+json"}, (
                operation_id,
                status,
            )

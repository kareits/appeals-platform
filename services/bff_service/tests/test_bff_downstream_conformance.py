"""Dereferenced cross-contract conformance between the BFF and the IAM/Ticket contracts.

Serving the committed BFF document as ``/openapi.json`` guarantees document identity but not that it
faithfully projects the upstream services it relays (CR-BFF-R5-MEDIUM-001). Every BFF proxy
operation forwards its request/response verbatim to a specific IAM or Ticket operation, so the BFF's
public wire contract must match that upstream operation exactly, and the gateway additions on top of
it must be declared explicitly rather than left to a loose "subset" rule (CR-BFF-R6-MEDIUM-001).

These tests fully dereference both documents and, per proxy operation, compare: the request body
(required flag, media types, schemas); every 2xx response's media types and schemas; path/query/
header parameters; the effective security requirement structure; the exact set of declared status
codes under a deterministic policy (upstream 2xx + relayed downstream client errors + gateway auth
401/403 + gateway ingress 413 for body operations + gateway transport 502/503/504); the
``application/problem+json`` RFC 7807 shape of every error; and the ``X-Correlation-ID`` header on
every response. Gateway-owned operations (``getAuthContext``, ``getTicketWorkspace``) have no
upstream counterpart and are excluded from the projection comparison but still must document the
correlation header. Negative drift tests prove each comparison fails when the corresponding upstream
or BFF field changes, so the projection cannot silently rot.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

_CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "openapi"
_BFF_PATH = _CONTRACTS / "bff-service.v1.yaml"
_TICKET_PATH = _CONTRACTS / "ticket-service.v1.yaml"
_IAM_PATH = _CONTRACTS / "iam-service.v1.yaml"

_CORRELATION_HEADER = "X-Correlation-ID"
_PROBLEM_MEDIA_TYPE = "application/problem+json"


def _load(path: Path) -> dict[str, Any]:
    """Load and parse an OpenAPI document.

    Args:
        path: The contract file path.

    Returns:
        The parsed specification.
    """
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


# Each BFF proxy operation and the upstream operation whose wire contract it must project exactly.
# (bff_method, bff_path, upstream_key, up_method, up_path)
_PROXY_OPERATIONS = [
    ("post", "/auth/login", "iam", "post", "/auth/login"),
    ("get", "/tickets", "ticket", "get", "/tickets"),
    ("post", "/tickets", "ticket", "post", "/tickets"),
    ("patch", "/tickets/{ticketId}", "ticket", "patch", "/tickets/{ticketId}"),
    ("post", "/tickets/{ticketId}/classify", "ticket", "post", "/tickets/{ticketId}/classify"),
    ("post", "/tickets/{ticketId}/decision", "ticket", "post", "/tickets/{ticketId}/decision"),
    ("post", "/tickets/{ticketId}/close", "ticket", "post", "/tickets/{ticketId}/close"),
    ("post", "/tickets/{ticketId}/legal-hold", "ticket", "post", "/tickets/{ticketId}/legal-hold"),
    ("post", "/tickets/{ticketId}/comments", "ticket", "post", "/tickets/{ticketId}/comments"),
    ("get", "/reference-data", "ticket", "get", "/reference-data"),
]


def _resolve_pointer(root: dict[str, Any], ref: str) -> Any:
    """Resolve a local JSON pointer of the form ``#/a/b/c`` against a document.

    Args:
        root: The document the pointer is relative to.
        ref: The local reference string.

    Returns:
        The referenced node.
    """
    node: Any = root
    for token in ref.lstrip("#/").split("/"):
        node = node[token]
    return node


def _deref(root: dict[str, Any], node: Any, stack: tuple[str, ...] = ()) -> Any:
    """Recursively inline every local ``$ref`` in a node, yielding a self-contained structure.

    Args:
        root: The document that references resolve against.
        node: The node to dereference.
        stack: The chain of references currently being expanded (cycle guard).

    Returns:
        The fully dereferenced node (a plain dict/list/scalar tree).
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in stack:  # pragma: no cover - contracts are acyclic today
                return {"$circular": ref}
            return _deref(root, _resolve_pointer(root, ref), (*stack, ref))
        return {key: _deref(root, value, stack) for key, value in node.items()}
    if isinstance(node, list):
        return [_deref(root, item, stack) for item in node]
    return node


def _operation(spec: dict[str, Any], method: str, path: str) -> tuple[dict[str, Any], list[Any]]:
    """Return an operation object and its effective parameters (path-level plus operation-level).

    Args:
        spec: The OpenAPI document.
        method: The HTTP method (lowercase).
        path: The path key.

    Returns:
        The operation object and the merged parameter list.
    """
    path_item = spec["paths"][path]
    operation = path_item[method]
    params = list(path_item.get("parameters", [])) + list(operation.get("parameters", []))
    return operation, params


def _request_projection(spec: dict[str, Any], operation: dict[str, Any]) -> Any:
    """Return the dereferenced request-body projection (required flag, media types, schemas).

    Args:
        spec: The document the operation belongs to.
        operation: The operation object.

    Returns:
        ``None`` when there is no request body, otherwise the projection.
    """
    body = operation.get("requestBody")
    if body is None:
        return None
    return {
        "required": body.get("required", False),
        "content": {
            media: _deref(spec, content["schema"]) for media, content in body["content"].items()
        },
    }


def _success_projection(spec: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    """Return the dereferenced 2xx response projection keyed by status code.

    Args:
        spec: The document the operation belongs to.
        operation: The operation object.

    Returns:
        A mapping of 2xx status code to its media-type/schema projection.
    """
    out: dict[str, Any] = {}
    for code, response in operation["responses"].items():
        if code.startswith("2"):
            content = _deref(spec, response).get("content", {})
            out[code] = {media: entry["schema"] for media, entry in content.items()}
    return out


def _param_projection(spec: dict[str, Any], params: list[Any]) -> dict[tuple[str, str], Any]:
    """Return a dereferenced parameter projection keyed by ``(name, location)``.

    Args:
        spec: The document the parameters belong to.
        params: The merged parameter list.

    Returns:
        A mapping of ``(name, in)`` to its required flag and schema.
    """
    out: dict[tuple[str, str], Any] = {}
    for param in params:
        resolved = _deref(spec, param)
        out[(resolved["name"], resolved["in"])] = {
            "required": resolved.get("required", False),
            "schema": _deref(spec, resolved.get("schema", {})),
        }
    return out


def _security_requirement(spec: dict[str, Any], operation: dict[str, Any]) -> list[Any]:
    """Return the effective security requirement structure of an operation.

    Args:
        spec: The document the operation belongs to.
        operation: The operation object.

    Returns:
        The operation-level security requirement, or the document default, or an empty list.
    """
    requirement = operation.get("security", spec.get("security"))
    return cast(list[Any], requirement or [])


def _declared_status_codes(operation: dict[str, Any]) -> set[str]:
    """Return the set of status codes an operation declares.

    Args:
        operation: The operation object.

    Returns:
        The declared status-code strings.
    """
    return set(operation["responses"].keys())


def _expected_status_codes(up_op: dict[str, Any], *, has_request_body: bool) -> set[str]:
    """Compute the exact status codes a BFF proxy operation must declare (deterministic policy).

    The policy is: upstream 2xx codes (relayed successes) + upstream 4xx codes (relayed downstream
    client errors) + gateway authentication 401/403 + the gateway ingress 413 for operations that
    accept a body + gateway transport 502/503/504.

    Args:
        up_op: The upstream operation object.
        has_request_body: Whether the BFF operation accepts a request body.

    Returns:
        The expected set of status-code strings.
    """
    upstream = _declared_status_codes(up_op)
    up_2xx = {code for code in upstream if code.startswith("2")}
    up_client_errors = {code for code in upstream if code.startswith("4")}
    gateway = {"401", "403", "502", "503", "504"}
    if has_request_body:
        gateway |= {"413"}
    return up_2xx | up_client_errors | gateway


def _error_shape_ok(spec: dict[str, Any], operation: dict[str, Any]) -> bool:
    """Return whether every 4xx/5xx response is an RFC 7807 ``application/problem+json`` Problem.

    Args:
        spec: The document the operation belongs to.
        operation: The operation object.

    Returns:
        ``True`` when all error responses use the Problem media type and schema.
    """
    problem_schema = _deref(spec, spec["components"]["schemas"]["Problem"])
    for code, response in operation["responses"].items():
        if code[0] not in {"4", "5"}:
            continue
        content = _deref(spec, response).get("content", {})
        if set(content) != {_PROBLEM_MEDIA_TYPE}:
            return False
        if content[_PROBLEM_MEDIA_TYPE]["schema"] != problem_schema:
            return False
    return True


def _all_responses_declare_correlation(spec: dict[str, Any], operation: dict[str, Any]) -> bool:
    """Return whether every response of an operation declares the ``X-Correlation-ID`` header.

    Args:
        spec: The document the operation belongs to.
        operation: The operation object.

    Returns:
        ``True`` when the correlation header is declared on every response.
    """
    for response in operation["responses"].values():
        headers = _deref(spec, response).get("headers", {})
        if _CORRELATION_HEADER not in headers:
            return False
    return True


@pytest.fixture(scope="module")
def contracts() -> dict[str, dict[str, Any]]:
    """Load the BFF, Ticket and IAM contracts once for the module.

    Returns:
        A mapping of contract key to parsed document.
    """
    return {"bff": _load(_BFF_PATH), "ticket": _load(_TICKET_PATH), "iam": _load(_IAM_PATH)}


@pytest.mark.parametrize(
    ("bff_method", "bff_path", "upstream", "up_method", "up_path"),
    _PROXY_OPERATIONS,
    ids=[f"{m.upper()} {p}" for m, p, *_ in _PROXY_OPERATIONS],
)
def test_proxy_operation_matches_upstream_wire_contract(
    contracts: dict[str, dict[str, Any]],
    bff_method: str,
    bff_path: str,
    upstream: str,
    up_method: str,
    up_path: str,
) -> None:
    """Each BFF proxy operation projects the upstream request/response/status/headers/security."""
    bff = contracts["bff"]
    up = contracts[upstream]
    bff_op, bff_params = _operation(bff, bff_method, bff_path)
    up_op, up_params = _operation(up, up_method, up_path)

    # Request body: same required flag, media types and dereferenced schemas.
    assert _request_projection(bff, bff_op) == _request_projection(up, up_op)

    # Every upstream 2xx response is projected identically by the BFF (exact 2xx set and schemas).
    bff_success = _success_projection(bff, bff_op)
    up_success = _success_projection(up, up_op)
    assert set(bff_success) == set(up_success), (bff_path, set(bff_success), set(up_success))
    assert bff_success == up_success, bff_path

    # Every upstream parameter appears on the BFF with an identical schema, and the query-parameter
    # sets match exactly (the BFF hides no upstream filter).
    bff_pp = _param_projection(bff, bff_params)
    up_pp = _param_projection(up, up_params)
    for key, projection in up_pp.items():
        assert bff_pp.get(key) == projection, (bff_path, key)
    assert {n for (n, loc) in bff_pp if loc == "query"} == {
        n for (n, loc) in up_pp if loc == "query"
    }, bff_path

    # The full effective security requirement structure matches (not just the scheme names).
    assert _security_requirement(bff, bff_op) == _security_requirement(up, up_op), bff_path

    # The exact declared status set follows the deterministic gateway policy.
    has_body = bff_op.get("requestBody") is not None
    assert _declared_status_codes(bff_op) == _expected_status_codes(
        up_op, has_request_body=has_body
    ), (bff_path, _declared_status_codes(bff_op))

    # Every error is a sanitized RFC 7807 problem; every response declares the correlation header.
    assert _error_shape_ok(bff, bff_op), bff_path
    assert _all_responses_declare_correlation(bff, bff_op), bff_path


def test_problem_schema_matches_upstream(contracts: dict[str, dict[str, Any]]) -> None:
    """The RFC 7807 Problem schema is identical across the BFF, Ticket and IAM contracts."""
    bff_problem = _deref(contracts["bff"], contracts["bff"]["components"]["schemas"]["Problem"])
    ticket_problem = _deref(
        contracts["ticket"], contracts["ticket"]["components"]["schemas"]["Problem"]
    )
    iam_problem = _deref(contracts["iam"], contracts["iam"]["components"]["schemas"]["Problem"])
    assert bff_problem == ticket_problem == iam_problem


def test_every_bff_response_declares_the_correlation_header(
    contracts: dict[str, dict[str, Any]],
) -> None:
    """Every response of every BFF operation (including gateway-owned ones) documents the header."""
    bff = contracts["bff"]
    for path_item in bff["paths"].values():
        for method, operation in path_item.items():
            if method in {"get", "post", "patch", "put", "delete"}:
                assert _all_responses_declare_correlation(bff, operation), (method, operation)


def test_proxy_bodies_are_not_open_ended(contracts: dict[str, dict[str, Any]]) -> None:
    """No proxied request/response schema uses ``additionalProperties: true`` (regression guard)."""
    bff = contracts["bff"]

    def _has_open_object(node: Any) -> bool:
        """Return whether a dereferenced schema tree permits arbitrary properties anywhere.

        Args:
            node: The schema node to scan.

        Returns:
            ``True`` if any object node sets ``additionalProperties: true``.
        """
        if isinstance(node, dict):
            if node.get("additionalProperties") is True:
                return True
            return any(_has_open_object(value) for value in node.values())
        if isinstance(node, list):
            return any(_has_open_object(item) for item in node)
        return False

    for bff_method, bff_path, *_ in _PROXY_OPERATIONS:
        operation, _params = _operation(bff, bff_method, bff_path)
        assert not _has_open_object(_request_projection(bff, operation)), (bff_path, "request")
        assert not _has_open_object(_success_projection(bff, operation)), (bff_path, "response")


# --- Negative drift tests: each proves a specific comparison fails when a field changes. ---


def test_drift_downstream_request_field(contracts: dict[str, dict[str, Any]]) -> None:
    """A new upstream required request field makes the request projection stop matching."""
    bff = contracts["bff"]
    drifted = copy.deepcopy(contracts["ticket"])
    schema = drifted["components"]["schemas"]["CreateTicketRequest"]
    schema["required"] = [*schema["required"], "newMandatoryField"]
    schema["properties"]["newMandatoryField"] = {"type": "string"}
    bff_op, _ = _operation(bff, "post", "/tickets")
    up_op, _ = _operation(drifted, "post", "/tickets")
    assert _request_projection(bff, bff_op) != _request_projection(drifted, up_op)


def test_drift_request_enum_constraint(contracts: dict[str, dict[str, Any]]) -> None:
    """A changed upstream enum/constraint makes the request projection stop matching."""
    bff = contracts["bff"]
    drifted = copy.deepcopy(contracts["ticket"])
    drifted["components"]["schemas"]["ApplicantInput"]["properties"]["applicantType"]["enum"] = [
        "CONSUMER"
    ]
    bff_op, _ = _operation(bff, "post", "/tickets")
    up_op, _ = _operation(drifted, "post", "/tickets")
    assert _request_projection(bff, bff_op) != _request_projection(drifted, up_op)


def test_drift_success_status(contracts: dict[str, dict[str, Any]]) -> None:
    """Dropping a BFF success status breaks the exact status-set and 2xx-schema comparison."""
    bff = copy.deepcopy(contracts["bff"])
    del bff["paths"]["/tickets"]["post"]["responses"]["201"]
    up = contracts["ticket"]
    bff_op, _ = _operation(bff, "post", "/tickets")
    up_op, _ = _operation(up, "post", "/tickets")
    assert _declared_status_codes(bff_op) != _expected_status_codes(up_op, has_request_body=True)
    assert set(_success_projection(bff, bff_op)) != set(_success_projection(up, up_op))


def test_drift_downstream_error_status(contracts: dict[str, dict[str, Any]]) -> None:
    """A new upstream client-error status the BFF has not adopted breaks the status-set policy."""
    bff = contracts["bff"]
    drifted = copy.deepcopy(contracts["ticket"])
    drifted["paths"]["/tickets"]["get"]["responses"]["418"] = {
        "$ref": "#/components/responses/Problem"
    }
    bff_op, _ = _operation(bff, "get", "/tickets")
    up_op, _ = _operation(drifted, "get", "/tickets")
    assert _declared_status_codes(bff_op) != _expected_status_codes(up_op, has_request_body=False)


def test_drift_error_media_type(contracts: dict[str, dict[str, Any]]) -> None:
    """Changing an error media type away from problem+json breaks the error-shape check."""
    bff = copy.deepcopy(contracts["bff"])
    # Redefine the shared Problem response to a non-problem media type.
    bff["components"]["responses"]["Problem"]["content"] = {
        "application/json": {"schema": {"$ref": "#/components/schemas/Problem"}}
    }
    bff_op, _ = _operation(bff, "post", "/tickets")
    assert not _error_shape_ok(bff, bff_op)


def test_drift_missing_correlation_header(contracts: dict[str, dict[str, Any]]) -> None:
    """Removing the correlation header from a response breaks the header check."""
    bff = copy.deepcopy(contracts["bff"])
    del bff["paths"]["/tickets"]["get"]["responses"]["200"]["headers"]
    bff_op, _ = _operation(bff, "get", "/tickets")
    assert not _all_responses_declare_correlation(bff, bff_op)


def test_drift_security_requirement(contracts: dict[str, dict[str, Any]]) -> None:
    """A changed upstream security requirement makes the security comparison fail."""
    bff = contracts["bff"]
    drifted = copy.deepcopy(contracts["ticket"])
    drifted["security"] = []
    bff_op, _ = _operation(bff, "post", "/tickets/{ticketId}/comments")
    up_op, _ = _operation(drifted, "post", "/tickets/{ticketId}/comments")
    assert _security_requirement(bff, bff_op) != _security_requirement(drifted, up_op)


def test_drift_query_parameter(contracts: dict[str, dict[str, Any]]) -> None:
    """A changed upstream query-parameter schema makes the parameter comparison fail."""
    bff = contracts["bff"]
    drifted = copy.deepcopy(contracts["ticket"])
    for param in drifted["paths"]["/tickets"]["get"]["parameters"]:
        if isinstance(param, dict) and param.get("name") == "page":
            param["schema"] = {"type": "string"}
    _bff_op, bff_params = _operation(bff, "get", "/tickets")
    _up_op, up_params = _operation(drifted, "get", "/tickets")
    assert _param_projection(bff, bff_params) != _param_projection(drifted, up_params)

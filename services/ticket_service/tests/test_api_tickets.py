"""Integration tests for the ticket HTTP API via the ASGI client."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

import yaml
from httpx import AsyncClient
from ticket_service.config import Settings
from ticket_service.main import create_app

_CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "ticket-service.v1.yaml"


def _create_body(**overrides: Any) -> dict[str, Any]:
    """Build a camelCase create-ticket request body.

    Args:
        **overrides: Top-level fields to override.

    Returns:
        The request body.
    """
    body: dict[str, Any] = {
        "receivedAt": "2026-07-22T09:00:00Z",
        "sourceChannelCode": "EMAIL",
        "subject": "Restructuring request",
        "description": "Full appeal text",
        "productCode": "MICROLOAN",
        "classifierCode": "RESTRUCTURING",
        "priorityCode": "NORMAL",
        "contractNumber": "C-1",
        "applicant": {
            "applicantType": "CONSUMER",
            "dataSource": "MANUAL",
            "fullName": "Иванов Иван",
            "identifierType": "IIN",
            "identifierValue": "900101300123",
        },
    }
    body.update(overrides)
    return body


async def test_create_returns_masked_card(client: AsyncClient) -> None:
    """Registration returns 201 with a registration number and a masked identifier."""
    response = await client.post("/api/v1/tickets", json=_create_body())

    assert response.status_code == 201
    body = response.json()
    assert body["registrationNumber"] == "AP-2026-000001"
    assert body["version"] == 1
    assert body["applicants"][0]["identifierMasked"] == "********0123"
    assert "identifierValue" not in body["applicants"][0]
    assert "900101300123" not in response.text


async def test_get_and_search(client: AsyncClient) -> None:
    """A registered ticket can be fetched by id and found by identifier search."""
    created = (await client.post("/api/v1/tickets", json=_create_body())).json()
    ticket_id = created["id"]

    got = await client.get(f"/api/v1/tickets/{ticket_id}")
    assert got.status_code == 200

    found = await client.get("/api/v1/tickets", params={"identifierValue": "900101300123"})
    assert found.status_code == 200
    page = found.json()
    assert page["page"]["total"] == 1
    assert page["items"][0]["id"] == ticket_id


async def test_classify_bumps_version(client: AsyncClient) -> None:
    """Classifying updates the codes and increments the version."""
    created = (await client.post("/api/v1/tickets", json=_create_body())).json()
    ticket_id = created["id"]

    response = await client.post(
        f"/api/v1/tickets/{ticket_id}/classify",
        json={
            "expectedVersion": 1,
            "productCode": "INSTALLMENT",
            "classifierCode": "COMPLAINT",
            "priorityCode": "HIGH",
        },
    )
    assert response.status_code == 200
    assert response.json()["classifierCode"] == "COMPLAINT"
    assert response.json()["version"] == 2


async def test_update_version_conflict_returns_409(client: AsyncClient) -> None:
    """A stale expectedVersion yields an RFC 7807 conflict."""
    created = (await client.post("/api/v1/tickets", json=_create_body())).json()
    ticket_id = created["id"]

    response = await client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"expectedVersion": 99, "subject": "New"},
    )
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_get_missing_ticket_returns_404(client: AsyncClient) -> None:
    """Fetching an unknown ticket yields a Problem Details 404."""
    response = await client.get(f"/api/v1/tickets/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_comments_roundtrip(client: AsyncClient) -> None:
    """A comment can be posted and then listed."""
    created = (await client.post("/api/v1/tickets", json=_create_body())).json()
    ticket_id = created["id"]

    posted = await client.post(f"/api/v1/tickets/{ticket_id}/comments", json={"body": "Note"})
    assert posted.status_code == 201

    listed = await client.get(f"/api/v1/tickets/{ticket_id}/comments")
    assert listed.status_code == 200
    comments = listed.json()
    assert len(comments) == 1
    assert comments[0]["body"] == "Note"


async def test_reference_data_lists_active_entries(client: AsyncClient) -> None:
    """Reference data returns active entries ordered by type, then sort order, then code."""
    response = await client.get("/api/v1/reference-data")

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert entries, "expected seeded reference entries"
    # Every entry carries the contracted shape.
    first = entries[0]
    assert {"dictionaryType", "code", "displayNameRu", "displayNameKk", "sortOrder"} <= set(first)
    # A known product code is present with its Russian business label.
    products = {e["code"]: e for e in entries if e["dictionaryType"] == "product"}
    assert products["MICROLOAN"]["displayNameRu"] == "Микрокредит"
    # Ordering is deterministic: grouped by type, then ascending sort order within a type.
    product_orders = [e["sortOrder"] for e in entries if e["dictionaryType"] == "product"]
    assert product_orders == sorted(product_orders)


async def test_reference_data_filters_by_types(client: AsyncClient) -> None:
    """The types filter restricts the response to the requested dictionaries."""
    response = await client.get("/api/v1/reference-data", params={"types": "product,priority"})

    assert response.status_code == 200
    returned_types = {e["dictionaryType"] for e in response.json()["entries"]}
    assert returned_types == {"product", "priority"}


async def test_reference_data_requires_authentication(unauth_client: AsyncClient) -> None:
    """Reference data requires a bearer token like every other ticket route."""
    response = await unauth_client.get("/api/v1/reference-data")
    assert response.status_code == 401


async def test_idempotent_create_returns_200_on_replay(client: AsyncClient) -> None:
    """Repeating a create with the same Idempotency-Key returns the original with HTTP 200."""
    headers = {"Idempotency-Key": "abc-123"}
    first = await client.post("/api/v1/tickets", json=_create_body(), headers=headers)
    second = await client.post("/api/v1/tickets", json=_create_body(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_decision_then_close_flow(client: AsyncClient) -> None:
    """Registration, decision, and close succeed and set retention and terminal status."""
    ticket_id = (await client.post("/api/v1/tickets", json=_create_body())).json()["id"]

    decided = await client.post(
        f"/api/v1/tickets/{ticket_id}/decision",
        json={
            "expectedVersion": 1,
            "decisionCode": "REJECTED",
            "decisionText": "Rationale",
        },
    )
    assert decided.status_code == 200
    assert decided.json()["version"] == 2

    closed = await client.post(
        f"/api/v1/tickets/{ticket_id}/close",
        json={
            "expectedVersion": 2,
            "closureReasonCode": "RESOLVED",
            "responseSentAt": "2026-07-23T09:00:00Z",
        },
    )
    assert closed.status_code == 200
    body = closed.json()
    assert body["currentStatusCode"] == "COMPLETED"
    assert body["retentionUntil"] is not None


async def test_close_without_decision_returns_422(client: AsyncClient) -> None:
    """Closing before a decision is recorded yields an RFC 7807 422."""
    ticket_id = (await client.post("/api/v1/tickets", json=_create_body())).json()["id"]

    response = await client.post(
        f"/api/v1/tickets/{ticket_id}/close",
        json={"expectedVersion": 1, "closureReasonCode": "RESOLVED", "noResponseReason": "n/a"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_set_legal_hold(client: AsyncClient) -> None:
    """A legal hold can be placed via the API."""
    ticket_id = (await client.post("/api/v1/tickets", json=_create_body())).json()["id"]

    response = await client.post(
        f"/api/v1/tickets/{ticket_id}/legal-hold",
        json={"expectedVersion": 1, "legalHold": True, "reason": "Litigation"},
    )
    assert response.status_code == 200
    assert response.json()["legalHold"] is True


async def test_create_sets_sla_due_dates(client: AsyncClient) -> None:
    """Registration computes and returns the SLA deadlines and policy version."""
    body = (await client.post("/api/v1/tickets", json=_create_body())).json()

    assert body["internalDueAt"] is not None
    assert body["legalDueAt"] is not None
    assert body["slaPolicyVersion"] == "v1-temp"


async def test_camelcase_search_filter_actually_narrows_results(client: AsyncClient) -> None:
    """A camelCase identifierValue filter narrows across multiple tickets (CR-HIGH-002)."""
    first = _create_body()
    first["applicant"]["identifierValue"] = "900101300123"
    second = _create_body()
    second["applicant"]["identifierValue"] = "111111111111"
    await client.post("/api/v1/tickets", json=first)
    await client.post("/api/v1/tickets", json=second)

    page = (await client.get("/api/v1/tickets", params={"identifierValue": "900101300123"})).json()
    assert page["page"]["total"] == 1
    assert page["items"][0]["registrationNumber"] == "AP-2026-000001"


async def test_naive_received_at_is_rejected(client: AsyncClient) -> None:
    """A timezone-naive receivedAt is rejected with 422 (CR-MEDIUM-001)."""
    response = await client.post(
        "/api/v1/tickets", json=_create_body(receivedAt="2026-07-22T09:00:00")
    )
    assert response.status_code == 422


async def test_wrong_applicant_role_is_rejected(client: AsyncClient) -> None:
    """A primary applicant labelled REPRESENTATIVE is rejected with 422 (CR-MEDIUM-002)."""
    body = _create_body()
    body["applicant"]["applicantType"] = "REPRESENTATIVE"
    response = await client.post("/api/v1/tickets", json=body)
    assert response.status_code == 422


async def test_unknown_reference_code_is_rejected(client: AsyncClient) -> None:
    """A product code absent from the dictionaries is rejected with 422 (CR-HIGH-006)."""
    response = await client.post("/api/v1/tickets", json=_create_body(productCode="NOT_A_PRODUCT"))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_oversized_code_is_rejected(client: AsyncClient) -> None:
    """An over-length coded value is rejected with 422, not deferred to the DB (CR-MEDIUM-002)."""
    response = await client.post("/api/v1/tickets", json=_create_body(sourceChannelCode="X" * 65))
    assert response.status_code == 422


# Request operations compared for runtime/committed contract parity (CR-MEDIUM-006).
_REQUEST_OPERATIONS = (
    "createManualTicket",
    "updateTicketDetails",
    "classifyTicket",
    "recordDecision",
    "closeTicket",
    "setLegalHold",
    "addComment",
)
_HTTP_METHODS = {"get", "post", "patch", "put", "delete"}


def _runtime_openapi() -> dict[str, Any]:
    """Build the runtime OpenAPI document from the FastAPI app.

    Returns:
        The generated OpenAPI document.
    """
    app = create_app(Settings(environment="test", database_url="sqlite+aiosqlite:///:memory:"))
    return dict(app.openapi())


def _contract() -> dict[str, Any]:
    """Load the committed OpenAPI contract.

    Returns:
        The parsed contract document.
    """
    return cast(dict[str, Any], yaml.safe_load(_CONTRACT.read_text(encoding="utf-8")))


def _operations_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index a spec's operations by operationId.

    Args:
        spec: An OpenAPI document.

    Returns:
        A mapping of operationId to the operation object.
    """
    return {
        operation["operationId"]: operation
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in _HTTP_METHODS
    }


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Resolve a top-level ``$ref`` against the component schemas.

    Args:
        schema: A schema that may be a ``$ref``.
        components: The component-schema map.

    Returns:
        The resolved schema.
    """
    if "$ref" in schema:
        return cast(dict[str, Any], components[schema["$ref"].split("/")[-1]])
    return schema


def _is_null_schema(node: dict[str, Any]) -> bool:
    """Return whether a schema node represents only the JSON ``null`` type.

    Args:
        node: The schema node.

    Returns:
        ``True`` if the node's only type is ``null``.
    """
    return node.get("type") == "null"


def _canonical(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Reduce a schema to a canonical, comparable form (ignoring titles/defaults/descriptions).

    Resolves ``$ref`` and normalizes nullable unions (runtime ``anyOf[X, null]`` and contract
    ``type: [X, "null"]``) to a single base plus a ``nullable`` flag, so runtime and committed
    schemas compare equal iff they are semantically equal. Recurses into object properties and array
    items and includes ``additionalProperties``, ``required``, and ``enum`` (null-stripped).

    Args:
        schema: The schema to canonicalize.
        components: The component-schema map for ``$ref`` resolution.

    Returns:
        The canonical representation.
    """
    schema = _resolve(schema, components)
    for branch_key in ("anyOf", "oneOf"):
        if branch_key in schema:
            branches = schema[branch_key]
            non_null = [b for b in branches if not _is_null_schema(_resolve(b, components))]
            nullable = any(_is_null_schema(_resolve(b, components)) for b in branches)
            base = _canonical(non_null[0], components) if non_null else {"types": []}
            base["nullable"] = base.get("nullable", False) or nullable
            return base

    raw_type = schema.get("type")
    types = [
        t for t in (raw_type if isinstance(raw_type, list) else [raw_type]) if t and t != "null"
    ]
    nullable = isinstance(raw_type, list) and "null" in raw_type
    result: dict[str, Any] = {"types": sorted(types), "nullable": nullable}
    if "enum" in schema:
        result["enum"] = sorted(str(v) for v in schema["enum"] if v is not None)
    for key in ("minLength", "maxLength", "minimum", "format"):
        if key in schema:
            result[key] = schema[key]
    if "object" in types or "properties" in schema:
        result["additionalProperties"] = schema.get("additionalProperties", True)
        result["required"] = sorted(schema.get("required", []))
        result["properties"] = {
            name: _canonical(sub, components) for name, sub in schema.get("properties", {}).items()
        }
    if "array" in types or "items" in schema:
        result["items"] = _canonical(schema["items"], components)
    return result


def test_search_query_params_match_committed_contract() -> None:
    """The runtime search query parameter names exactly equal the committed contract."""
    runtime = _runtime_openapi()
    runtime_query = {
        p["name"]
        for p in runtime["paths"]["/api/v1/tickets"]["get"]["parameters"]
        if p.get("in") == "query"
    }
    contract = _contract()
    contract_query = {
        p["name"]
        for p in contract["paths"]["/tickets"]["get"]["parameters"]
        if isinstance(p, dict) and p.get("in") == "query"
    }
    assert runtime_query == contract_query


def test_request_bodies_match_committed_contract() -> None:
    """Runtime request bodies match the committed contract, including additionalProperties/enums.

    Compares the fully canonicalized request schema per operation (types, nullability, enums,
    string/number constraints, additionalProperties, required, and nested referenced schemas), so
    unknown-field rejection and nested drift are caught (CR-MEDIUM-006).
    """
    runtime = _runtime_openapi()
    contract = _contract()
    runtime_ops = _operations_by_id(runtime)
    contract_ops = _operations_by_id(contract)
    runtime_components = runtime["components"]["schemas"]
    contract_components = contract["components"]["schemas"]

    for operation_id in _REQUEST_OPERATIONS:
        runtime_body = runtime_ops[operation_id]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        contract_body = contract_ops[operation_id]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        assert _canonical(runtime_body, runtime_components) == _canonical(
            contract_body, contract_components
        ), operation_id


async def test_unknown_request_property_is_rejected(client: AsyncClient) -> None:
    """An unknown body property is rejected with 422, matching additionalProperties=false."""
    response = await client.post("/api/v1/tickets", json=_create_body(unexpectedField="x"))
    assert response.status_code == 422

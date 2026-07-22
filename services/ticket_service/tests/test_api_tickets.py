"""Integration tests for the ticket HTTP API via the ASGI client."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient


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
    author = str(uuid.uuid4())

    posted = await client.post(
        f"/api/v1/tickets/{ticket_id}/comments", json={"authorId": author, "body": "Note"}
    )
    assert posted.status_code == 201

    listed = await client.get(f"/api/v1/tickets/{ticket_id}/comments")
    assert listed.status_code == 200
    comments = listed.json()
    assert len(comments) == 1
    assert comments[0]["body"] == "Note"


async def test_idempotent_create_returns_200_on_replay(client: AsyncClient) -> None:
    """Repeating a create with the same Idempotency-Key returns the original with HTTP 200."""
    headers = {"Idempotency-Key": "abc-123"}
    first = await client.post("/api/v1/tickets", json=_create_body(), headers=headers)
    second = await client.post("/api/v1/tickets", json=_create_body(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

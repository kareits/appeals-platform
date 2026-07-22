"""Contract tests for the ticket-service event payload schemas.

Verify that each payload schema (ticket.created/classified/updated v1) is a valid Draft 2020-12
schema, that representative sample payloads validate, that a payload wrapped in the shared envelope
conforms to the envelope schema, and that the created payload never exposes a full national
identifier (only a masked form) per ADR-006 / docs/06.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

EVENTS_DIR = Path(__file__).resolve().parents[1] / "events"
PAYLOAD_DIR = EVENTS_DIR / "payloads"
ENVELOPE_PATH = EVENTS_DIR / "event-envelope.v1.json"


def _load(path: Path) -> dict[str, Any]:
    """Load a JSON document from disk.

    Args:
        path: The file to read.

    Returns:
        The parsed JSON document.
    """
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sample_payloads() -> dict[str, dict[str, Any]]:
    """Build a representative valid payload for each ticket event.

    Returns:
        A mapping of schema filename to a conforming sample payload.
    """
    return {
        "ticket.created.v1.json": {
            "ticketId": "018f7b3c-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
            "registrationNumber": "AP-2026-000001",
            "receivedAt": "2026-07-22T09:00:00Z",
            "registeredAt": "2026-07-22T09:01:00Z",
            "sourceChannelCode": "EMAIL",
            "productCode": "MICROLOAN",
            "classifierCode": "RESTRUCTURING",
            "priorityCode": "NORMAL",
            "currentStatusCode": "NEW",
            "currentStageCode": "REGISTRATION",
            "subject": "Restructuring request",
            "contractNumber": None,
            "applicant": {
                "applicantType": "CONSUMER",
                "identifierType": "IIN",
                "identifierMasked": "******7890",
                "regionCode": None,
            },
            "hasRepresentative": False,
        },
        "ticket.classified.v1.json": {
            "ticketId": "018f7b3c-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
            "productCode": "MICROLOAN",
            "classifierCode": "RESTRUCTURING",
            "priorityCode": "HIGH",
        },
        "ticket.updated.v1.json": {
            "ticketId": "018f7b3c-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
            "changedFields": ["subject", "contractNumber"],
        },
    }


@pytest.mark.parametrize(
    "filename", ["ticket.created.v1.json", "ticket.classified.v1.json", "ticket.updated.v1.json"]
)
def test_payload_schema_is_valid(filename: str) -> None:
    """Each payload schema is itself a valid Draft 2020-12 schema."""
    Draft202012Validator.check_schema(_load(PAYLOAD_DIR / filename))


@pytest.mark.parametrize(
    "filename", ["ticket.created.v1.json", "ticket.classified.v1.json", "ticket.updated.v1.json"]
)
def test_sample_payload_validates(filename: str) -> None:
    """The representative sample payload conforms to its schema."""
    schema = _load(PAYLOAD_DIR / filename)
    Draft202012Validator(schema).validate(_sample_payloads()[filename])


@pytest.mark.parametrize(
    "filename", ["ticket.created.v1.json", "ticket.classified.v1.json", "ticket.updated.v1.json"]
)
def test_payload_in_envelope_validates(filename: str) -> None:
    """A payload wrapped in the shared envelope conforms to the envelope schema."""
    envelope_schema = _load(ENVELOPE_PATH)
    event_type = filename.replace(".json", "")
    envelope = {
        "eventId": "018f7b3c-1a2b-7c3d-8e4f-5a6b7c8d9e0f",
        "eventType": event_type,
        "eventVersion": 1,
        "occurredAt": "2026-07-22T09:01:00Z",
        "producer": "ticket-service",
        "correlationId": "11111111-2222-3333-4444-555555555555",
        "causationId": None,
        "payload": _sample_payloads()[filename],
    }
    Draft202012Validator(envelope_schema).validate(envelope)


def test_created_payload_never_exposes_full_identifier() -> None:
    """The created payload carries only a masked identifier, never the full value (docs/06)."""
    schema = _load(PAYLOAD_DIR / "ticket.created.v1.json")
    top_level = schema["properties"]
    applicant = top_level["applicant"]["properties"]
    assert "identifierValue" not in top_level
    assert "identifierValue" not in applicant
    assert "identifierMasked" in applicant

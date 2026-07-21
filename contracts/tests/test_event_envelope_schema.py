"""Contract tests for the event-envelope JSON Schema.

Verify that the schema is a valid Draft 2020-12 schema, that a well-formed event passes, and that
malformed or non-canonical events are rejected (ADR-006 / ADR-0004).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "events" / "event-envelope.v1.json"


def _load_schema() -> dict[str, Any]:
    """Load the event-envelope JSON Schema from disk.

    Returns:
        The parsed schema document.
    """
    return cast(dict[str, Any], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _valid_event() -> dict[str, Any]:
    """Build a syntactically valid sample event.

    Returns:
        An envelope that conforms to the schema.
    """
    return {
        "eventId": "3f1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8",
        "eventType": "ticket.created.v1",
        "eventVersion": 1,
        "occurredAt": "2026-01-01T00:00:00Z",
        "producer": "ticket-service",
        "correlationId": "11111111-2222-3333-4444-555555555555",
        "causationId": None,
        "payload": {"ticketId": "9a8b7c6d-5e4f-3021-1234-567890abcdef"},
    }


def test_schema_is_valid() -> None:
    """The envelope schema is itself a valid Draft 2020-12 schema."""
    Draft202012Validator.check_schema(_load_schema())


def test_valid_event_passes() -> None:
    """A well-formed event conforms to the envelope schema."""
    Draft202012Validator(_load_schema()).validate(_valid_event())


def test_missing_required_field_fails() -> None:
    """An event missing a required field is rejected."""
    event = _valid_event()
    del event["eventId"]
    with pytest.raises(ValidationError):
        Draft202012Validator(_load_schema()).validate(event)


def test_forbidden_namespace_is_rejected() -> None:
    """An event using the forbidden email.* namespace is rejected (ADR-006)."""
    event = _valid_event()
    event["eventType"] = "email.sent.v1"
    with pytest.raises(ValidationError):
        Draft202012Validator(_load_schema()).validate(event)


def test_additional_properties_are_rejected() -> None:
    """An event carrying an unknown top-level field is rejected."""
    event = _valid_event()
    event["unexpected"] = "value"
    with pytest.raises(ValidationError):
        Draft202012Validator(_load_schema()).validate(event)

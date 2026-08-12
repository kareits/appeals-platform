"""Contract test for the ticket-service OpenAPI document.

Validates that the spec conforms to the OpenAPI 3.1 specification and that the expected operations
are present, so the contract stays authoritative and consistent (contract-first, docs/05).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from openapi_spec_validator import validate

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi" / "ticket-service.v1.yaml"


def _load_spec() -> dict[str, Any]:
    """Load the OpenAPI document from disk.

    Returns:
        The parsed specification.
    """
    return cast(dict[str, Any], yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8")))


def test_spec_is_valid_openapi() -> None:
    """The document is a valid OpenAPI 3.1 specification."""
    validate(_load_spec())


def test_expected_operations_present() -> None:
    """The spec declares the TASK_01B operations."""
    spec = _load_spec()
    operation_ids = {
        operation["operationId"]
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "patch", "put", "delete"}
    }
    assert {
        "createManualTicket",
        "searchTickets",
        "getTicket",
        "updateTicketDetails",
        "classifyTicket",
        "recordDecision",
        "closeTicket",
        "setLegalHold",
        "addComment",
        "listComments",
        "listReferenceData",
        # Read-only authorization probe consumed by the Document Service (CR-DOC-HIGH-002).
        "getTicketAccess",
    } <= operation_ids

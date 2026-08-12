"""Contract test for the document-service OpenAPI document.

Validates that the spec conforms to the OpenAPI 3.1 specification and that the expected operations
and security expectations are present, so the contract stays authoritative and consistent
(contract-first, docs/05).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from openapi_spec_validator import validate

SPEC_PATH = Path(__file__).resolve().parents[1] / "openapi" / "document-service.v1.yaml"

_HTTP_METHODS = {"get", "post", "patch", "put", "delete"}


def _load_spec() -> dict[str, Any]:
    """Load the OpenAPI document from disk.

    Returns:
        The parsed specification.
    """
    return cast(dict[str, Any], yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8")))


def _operations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index the spec's operations by operationId.

    Args:
        spec: The parsed specification.

    Returns:
        A mapping of operationId to operation object.
    """
    return {
        operation["operationId"]: operation
        for path_item in spec["paths"].values()
        for method, operation in path_item.items()
        if method in _HTTP_METHODS
    }


def test_spec_is_valid_openapi() -> None:
    """The document is a valid OpenAPI 3.1 specification."""
    validate(_load_spec())


def test_expected_operations_present() -> None:
    """The spec declares the TASK_03A-1 operations."""
    assert {
        "uploadDocument",
        "getDocument",
        "downloadDocument",
        "listTicketDocuments",
        "linkDocument",
    } <= _operations(_load_spec()).keys()


def test_all_operations_require_bearer_authentication() -> None:
    """Every operation is protected: the document service is a security boundary of its own.

    The spec applies ``bearerAuth`` globally and no operation opts out with an empty security list,
    so no document operation is reachable without a verified token (CR-BFF-BLOCKER-001 precedent).
    """
    spec = _load_spec()
    assert spec["security"] == [{"bearerAuth": []}]
    assert all("security" not in operation for operation in _operations(spec).values())


def test_download_is_streamed_as_an_untrusted_attachment() -> None:
    """The download operation returns binary content, never a browser-renderable media type."""
    download = _operations(_load_spec())["downloadDocument"]
    content = download["responses"]["200"]["content"]
    assert set(content) == {"application/octet-stream"}
    # OpenAPI 3.1 (JSON Schema 2020-12) expresses a binary payload with ``contentMediaType``.
    schema = content["application/octet-stream"]["schema"]
    assert schema["contentMediaType"] == "application/octet-stream"
    assert {"Content-Disposition", "X-Content-Type-Options"} <= set(
        download["responses"]["200"]["headers"]
    )

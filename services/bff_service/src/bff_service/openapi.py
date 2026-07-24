"""Serve the committed OpenAPI contract as the authoritative runtime document.

Transparent-proxy routes return a bare ``Response``, so FastAPI cannot faithfully generate their
request/response bodies, success-code pairs, or RFC 7807 media types. Rather than duplicate the
Ticket/IAM wire schemas in code, the gateway serves the hand-written committed contract verbatim as
its runtime OpenAPI (``/openapi.json``). Runtime and committed documents are then identical by
construction — the class of drift the parity checks used to chase disappears — and a conformance
test asserts the app's routes and the contract's operations correspond exactly (CR-BFF-R4-MED-001).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

# Repository-relative location of the committed BFF contract. Resolved against the nearest ancestor
# that contains it, so it works in the repo (tests) and in the image (copied to /app/contracts).
_CONTRACT_RELATIVE = Path("contracts/openapi/bff-service.v1.yaml")


def _resolve_contract_path(explicit: str | None) -> Path:
    """Resolve the committed-contract path, searching ancestors when not given explicitly.

    Args:
        explicit: An explicit path override, or ``None`` to auto-discover.

    Returns:
        The path to the committed contract file.

    Raises:
        FileNotFoundError: When the contract cannot be located.
    """
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _CONTRACT_RELATIVE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"committed OpenAPI contract not found ({_CONTRACT_RELATIVE})")


@functools.cache
def committed_openapi(contract_path: str | None = None) -> dict[str, Any]:
    """Load and cache the committed BFF OpenAPI contract as a dictionary.

    Args:
        contract_path: An explicit path override, or ``None`` to auto-discover.

    Returns:
        The parsed committed OpenAPI document, served verbatim as the runtime schema.
    """
    path = _resolve_contract_path(contract_path)
    spec: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return spec

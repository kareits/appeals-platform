"""RFC 7807 response declarations for the document API.

FastAPI generates the runtime OpenAPI document from the route signatures, so the error responses a
route can return must be declared explicitly; otherwise the runtime document would advertise only
success codes and drift from the committed contract (which the parity test compares operation by
operation).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Problem(BaseModel):
    """RFC 7807 Problem Details body returned by every error response.

    Attributes:
        type: URI identifying the problem type; ``about:blank`` unless a specific type is defined.
        title: Short, human-readable summary of the problem type.
        status: The HTTP status code.
        detail: Occurrence-specific explanation, when available.
        instance: URI identifying the specific occurrence, when available.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


# Human-readable descriptions attached to the declared error codes, so the generated document
# explains each failure mode rather than repeating a generic label.
_DESCRIPTIONS = {
    400: "The request is malformed.",
    401: "Authentication is missing or invalid.",
    403: "The caller lacks the required permission.",
    404: "The document does not exist.",
    409: "The document's current state does not allow the operation.",
    413: "The upload exceeds the configured size limit.",
    422: "The request failed validation.",
    500: "The storage backend failed.",
    503: "The appeal-scope authorization decision is unavailable.",
}


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Build the ``responses`` mapping declaring RFC 7807 errors for a route.

    Args:
        *codes: The HTTP status codes the route can return as a problem document.

    Returns:
        A FastAPI ``responses`` mapping using the ``application/problem+json`` media type.
    """
    return {
        code: {
            "description": _DESCRIPTIONS[code],
            "content": {"application/problem+json": {"schema": Problem.model_json_schema()}},
        }
        for code in codes
    }

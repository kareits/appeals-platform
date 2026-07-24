"""RFC 7807 Problem Details error handling.

Provides a Problem Details data model, an exception that carries it, and Starlette exception
handlers that render errors as ``application/problem+json`` responses. Centralizing this keeps
error responses consistent across services (per the API conventions in the source requirements).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

PROBLEM_CONTENT_TYPE = "application/problem+json"
"""Media type for RFC 7807 Problem Details responses."""


@dataclass(frozen=True)
class ProblemDetail:
    """An RFC 7807 Problem Details payload.

    Attributes:
        title: A short, human-readable summary of the problem type.
        status: The HTTP status code.
        detail: A human-readable explanation specific to this occurrence.
        type: A URI reference identifying the problem type.
        instance: A URI reference identifying the specific occurrence.
    """

    title: str
    status: int
    detail: str | None = None
    type: str = "about:blank"
    instance: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the problem as a dictionary with empty fields removed.

        Returns:
            A mapping suitable for JSON serialization.
        """
        return {key: value for key, value in asdict(self).items() if value is not None}


class ProblemDetailError(Exception):
    """An exception carrying an RFC 7807 :class:`ProblemDetail` and optional response headers.

    Attributes:
        problem: The problem details to render in the response body.
        headers: Optional protocol headers to attach (for example, ``WWW-Authenticate`` on a 401).
    """

    def __init__(self, problem: ProblemDetail, headers: dict[str, str] | None = None) -> None:
        """Initialize the exception.

        Args:
            problem: The problem details to render in the response.
            headers: Optional response headers to attach (for example, an authentication challenge).
        """
        super().__init__(problem.detail or problem.title)
        self.problem = problem
        self.headers = headers


def _problem_response(
    problem: ProblemDetail, headers: dict[str, str] | None = None
) -> JSONResponse:
    """Build a Problem Details JSON response.

    Args:
        problem: The problem details to serialize.
        headers: Optional response headers to attach.

    Returns:
        A JSON response with the Problem Details media type.
    """
    return JSONResponse(
        problem.to_dict(),
        status_code=problem.status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def _handle_problem_detail(_: Request, exc: Exception) -> JSONResponse:
    """Render a :class:`ProblemDetailError` as a Problem Details response.

    Args:
        _: The incoming request (unused).
        exc: The raised exception; expected to be a :class:`ProblemDetailError`.

    Returns:
        A Problem Details JSON response.
    """
    assert isinstance(exc, ProblemDetailError)
    return _problem_response(exc.problem, exc.headers)


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    """Render a Starlette :class:`HTTPException` as a Problem Details response.

    Args:
        _: The incoming request (unused).
        exc: The raised exception; expected to be an :class:`HTTPException`.

    Returns:
        A Problem Details JSON response.
    """
    assert isinstance(exc, HTTPException)
    problem = ProblemDetail(title=exc.detail, status=exc.status_code)
    return _problem_response(problem)


def install_problem_detail_handlers(app: Starlette) -> None:
    """Register Problem Details exception handlers on a Starlette/FastAPI app.

    Args:
        app: The application to register handlers on.
    """
    app.add_exception_handler(ProblemDetailError, _handle_problem_detail)
    app.add_exception_handler(HTTPException, _handle_http_exception)

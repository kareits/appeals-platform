"""Fail-closed target guard shared by the destructive PostgreSQL tests.

The concurrency and migration tests drop schemas/tables, so pointing them at the wrong database
would destroy real data. This guard makes them opt-in and target-validated (CR-BFF-R6-MEDIUM-002):
they run only when ``ALLOW_DESTRUCTIVE_DATABASE_TESTS=1`` and ``TICKET_TEST_DATABASE_URL`` names an
obvious disposable test database (its name ends with ``_test`` and is not a system/application
database). If the opt-in is set but the target is unsafe the guard raises rather than silently
skipping, so a misconfiguration fails loudly instead of running against the wrong database. Each
concurrency run also confines its schema to a unique disposable namespace so cleanup stays in scope.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit

OPT_IN_ENV = "ALLOW_DESTRUCTIVE_DATABASE_TESTS"
URL_ENV = "TICKET_TEST_DATABASE_URL"

# A disposable test database must carry this name suffix and must not be a system/application name.
_SAFE_SUFFIX = "_test"
_FORBIDDEN_NAMES = frozenset(
    {"postgres", "template0", "template1", "ticket_service", "iam_service", "bff_service"}
)


def database_name(url: str) -> str:
    """Return the database name from a SQLAlchemy/PostgreSQL URL.

    Args:
        url: The database URL.

    Returns:
        The database name (the URL path without the leading slash or query string).
    """
    return urlsplit(url).path.lstrip("/").split("?", 1)[0]


def is_safe_test_target(url: str | None) -> bool:
    """Return whether a URL names an obvious disposable PostgreSQL test database.

    Args:
        url: The candidate database URL, or ``None``.

    Returns:
        ``True`` only for a PostgreSQL URL whose database name ends with ``_test`` and is not a
        known system or application database.
    """
    if not url or not url.startswith("postgresql"):
        return False
    name = database_name(url)
    return bool(name) and name.endswith(_SAFE_SUFFIX) and name not in _FORBIDDEN_NAMES


def destructive_tests_enabled() -> bool:
    """Return whether destructive PostgreSQL tests are opted in and a target URL is configured.

    Returns:
        ``True`` when the opt-in flag is set and a target URL is present (its safety is enforced
        separately by :func:`require_safe_test_url`, which fails closed on an unsafe target).
    """
    return os.environ.get(OPT_IN_ENV) == "1" and bool(os.environ.get(URL_ENV))


def require_safe_test_url() -> str:
    """Return the configured test URL, failing closed when it is not a safe disposable target.

    Returns:
        The validated test database URL.

    Raises:
        RuntimeError: When the target URL is missing or not an obvious disposable ``*_test``
            PostgreSQL database. The error is raised (not skipped) so a misconfigured opt-in run
            fails loudly instead of destroying the wrong database.
    """
    url = os.environ.get(URL_ENV)
    if not is_safe_test_target(url):
        raise RuntimeError(
            f"refusing to run a destructive database test against {url!r}: "
            f"{URL_ENV} must name a disposable PostgreSQL database whose name ends with "
            f"{_SAFE_SUFFIX!r} (for example 'ticket_service_test')"
        )
    assert url is not None
    return url


def unique_schema_name() -> str:
    """Return a unique, disposable schema name for a single destructive test run.

    Returns:
        A schema name namespaced so its create/drop cleanup can never reach another schema.
    """
    return f"ticket_test_{uuid.uuid4().hex[:12]}"

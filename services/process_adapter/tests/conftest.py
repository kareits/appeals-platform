"""Fixtures for Process Adapter tests.

The integration tests require a reachable Flowable instance and are skipped unless
``PA_FLOWABLE_BASE_URL`` is set (see the marker in the test module), so the default host test run
and the CI quality job stay green without Flowable. Run them via ``make spike``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from process_adapter.config import Settings
from process_adapter.infrastructure.flowable_client import FlowableClient


@pytest_asyncio.fixture
async def flowable_client() -> AsyncIterator[FlowableClient]:
    """Provide a Flowable client configured from the environment.

    Yields:
        A Flowable client bound to the configured REST service.
    """
    settings = Settings()
    client = FlowableClient(
        base_url=settings.flowable_base_url,
        username=settings.flowable_username,
        password=settings.flowable_password,
    )
    try:
        yield client
    finally:
        await client.aclose()

"""Application-level health checks for the Process Adapter."""

from __future__ import annotations

from process_adapter.infrastructure.flowable_client import FlowableClient


class FlowableHealthCheck:
    """Health check that verifies the Flowable REST API is reachable.

    Satisfies the ``mfo_observability.HealthCheck`` protocol (a ``name`` attribute and an async
    call returning a boolean).
    """

    name = "flowable"

    def __init__(self, client: FlowableClient) -> None:
        """Initialize the check.

        Args:
            client: The Flowable client to probe with.
        """
        self._client = client

    async def __call__(self) -> bool:
        """Check whether Flowable is reachable and authenticated.

        Returns:
            ``True`` if the Flowable REST API responds successfully.
        """
        return await self._client.is_available()

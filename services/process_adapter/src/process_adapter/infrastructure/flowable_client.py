"""Asynchronous client for the Flowable REST API.

Hides Flowable-specific endpoints and payloads behind a small set of methods used by the adapter.
This is the technical foundation validated by the TASK_00D spike; EP-3 builds the domain commands
on top of it.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

# Default timeout for Flowable REST calls, in seconds.
DEFAULT_TIMEOUT_SECONDS = 15.0


class FlowableClient:
    """A thin async client over the Flowable REST API.

    The client applies basic authentication and a default timeout. It is intended to be created
    once and closed on shutdown, or used as an async context manager.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: Base URL of the Flowable REST service.
            username: Basic-auth username.
            password: Basic-auth password.
            client: An optional pre-configured ``httpx.AsyncClient`` (useful for testing).
        """
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=httpx.BasicAuth(username, password),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    async def is_available(self) -> bool:
        """Return whether the Flowable REST API is reachable and authenticated.

        Returns:
            ``True`` if the process-definitions endpoint responds successfully.
        """
        try:
            response = await self._client.get("/repository/process-definitions", params={"size": 1})
        except httpx.HTTPError:
            return False
        return response.status_code == httpx.codes.OK

    async def deploy_process(self, filename: str, bpmn_xml: bytes) -> str:
        """Deploy a BPMN process definition.

        Args:
            filename: Deployment resource filename; must end with ``.bpmn20.xml`` or ``.bpmn``.
            bpmn_xml: The BPMN XML content.

        Returns:
            The created deployment identifier.
        """
        files = {"file": (filename, bpmn_xml, "text/xml")}
        response = await self._client.post("/repository/deployments", files=files)
        response.raise_for_status()
        return str(response.json()["id"])

    async def find_process_instance(self, business_key: str) -> dict[str, Any] | None:
        """Find a running process instance by business key.

        Args:
            business_key: The business key to search for.

        Returns:
            The instance object, or ``None`` if no instance has that business key.
        """
        response = await self._client.get(
            "/runtime/process-instances", params={"businessKey": business_key}
        )
        response.raise_for_status()
        data: list[dict[str, Any]] = response.json()["data"]
        return data[0] if data else None

    async def start_process(self, process_key: str, business_key: str) -> dict[str, Any]:
        """Start a process instance by definition key.

        Args:
            process_key: The process definition key.
            business_key: The business key to assign to the instance.

        Returns:
            The created process-instance object.
        """
        payload = {"processDefinitionKey": process_key, "businessKey": business_key}
        response = await self._client.post("/runtime/process-instances", json=payload)
        response.raise_for_status()
        return dict(response.json())

    async def list_tasks(self, process_instance_id: str) -> list[dict[str, Any]]:
        """List active user tasks for a process instance.

        Args:
            process_instance_id: The process instance identifier.

        Returns:
            The list of task objects.
        """
        response = await self._client.get(
            "/runtime/tasks", params={"processInstanceId": process_instance_id}
        )
        response.raise_for_status()
        tasks: list[dict[str, Any]] = response.json()["data"]
        return tasks

    async def claim_task(self, task_id: str, assignee: str) -> None:
        """Claim a user task for an assignee.

        Args:
            task_id: The task identifier.
            assignee: The user claiming the task.
        """
        response = await self._client.post(
            f"/runtime/tasks/{task_id}", json={"action": "claim", "assignee": assignee}
        )
        response.raise_for_status()

    async def complete_task(self, task_id: str) -> None:
        """Complete a user task.

        Args:
            task_id: The task identifier.
        """
        response = await self._client.post(f"/runtime/tasks/{task_id}", json={"action": "complete"})
        response.raise_for_status()

    async def find_message_execution(
        self, process_instance_id: str, message_name: str
    ) -> str | None:
        """Find an execution waiting on a message event.

        Args:
            process_instance_id: The process instance identifier.
            message_name: The message subscription name.

        Returns:
            The execution identifier, or ``None`` if no execution is waiting on the message.
        """
        response = await self._client.get(
            "/runtime/executions",
            params={
                "processInstanceId": process_instance_id,
                "messageEventSubscriptionName": message_name,
            },
        )
        response.raise_for_status()
        data: list[dict[str, Any]] = response.json()["data"]
        return str(data[0]["id"]) if data else None

    async def deliver_message(self, execution_id: str, message_name: str) -> None:
        """Deliver a message to a waiting execution (message correlation).

        Args:
            execution_id: The execution identifier waiting on the message.
            message_name: The message name to deliver.
        """
        response = await self._client.put(
            f"/runtime/executions/{execution_id}",
            json={"action": "messageEventReceived", "messageName": message_name},
        )
        response.raise_for_status()

    async def get_historic_process_instance(self, process_instance_id: str) -> dict[str, Any]:
        """Read the historic record of a process instance.

        Args:
            process_instance_id: The process instance identifier.

        Returns:
            The historic process-instance object (includes ``endTime`` once finished).
        """
        response = await self._client.get(
            f"/history/historic-process-instances/{process_instance_id}"
        )
        response.raise_for_status()
        return dict(response.json())

    async def list_historic_activities(self, process_instance_id: str) -> list[dict[str, Any]]:
        """List historic activity instances for a process instance.

        Args:
            process_instance_id: The process instance identifier.

        Returns:
            The list of historic activity-instance objects.
        """
        response = await self._client.get(
            "/history/historic-activity-instances",
            params={"processInstanceId": process_instance_id, "size": 100},
        )
        response.raise_for_status()
        activities: list[dict[str, Any]] = response.json()["data"]
        return activities

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> FlowableClient:
        """Enter the async context manager.

        Returns:
            This client instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the async context manager and close the client.

        Args:
            exc_type: The exception type raised in the context, if any.
            exc: The exception instance, if any.
            traceback: The traceback, if any.
        """
        await self.aclose()

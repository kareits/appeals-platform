"""Spike operations validating the Process Adapter ↔ Flowable loop (TASK_00D).

These high-level operations exercise the full technical cycle without a business process:
idempotent start by business key, user-task claim/complete, waiting for a timer to fire, message
correlation, and reading history. EP-3 replaces this with real domain commands.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from process_adapter.infrastructure.flowable_client import FlowableClient

# Message name and process key used by the spike BPMN (tests/resources/spike_process.bpmn20.xml).
SPIKE_PROCESS_KEY = "spikeProcess"
SPIKE_MESSAGE_NAME = "spikeMessage"


@dataclass
class StartResult:
    """Result of an idempotent start.

    Attributes:
        instance_id: The process instance identifier.
        created: ``True`` if a new instance was started, ``False`` if an existing one was reused.
    """

    instance_id: str
    created: bool


@dataclass
class SpikeResult:
    """Outcome of a full spike run.

    Attributes:
        instance_id: The process instance identifier.
        completed_task_id: The user task that was claimed and completed.
        activities: Activity ids recorded in history, in order.
        finished: ``True`` if the historic instance has an end time.
    """

    instance_id: str
    completed_task_id: str
    finished: bool
    activities: list[str] = field(default_factory=list)


async def start_process_idempotently(
    client: FlowableClient, business_key: str, process_key: str = SPIKE_PROCESS_KEY
) -> StartResult:
    """Start a process instance, reusing an existing one with the same business key.

    Args:
        client: The Flowable client.
        business_key: The business key that makes the start idempotent.
        process_key: The process definition key to start.

    Returns:
        The instance id and whether it was newly created.
    """
    existing = await client.find_process_instance(business_key)
    if existing is not None:
        return StartResult(instance_id=str(existing["id"]), created=False)
    instance = await client.start_process(process_key, business_key)
    return StartResult(instance_id=str(instance["id"]), created=True)


async def _wait_for_first_task(
    client: FlowableClient, instance_id: str, attempts: int = 20, delay: float = 0.5
) -> dict[str, Any]:
    """Poll until the process has an active user task.

    Args:
        client: The Flowable client.
        instance_id: The process instance identifier.
        attempts: Maximum number of polls.
        delay: Delay between polls, in seconds.

    Returns:
        The first active task object.

    Raises:
        TimeoutError: If no task appears within the allotted attempts.
    """
    for _ in range(attempts):
        tasks = await client.list_tasks(instance_id)
        if tasks:
            return tasks[0]
        await asyncio.sleep(delay)
    raise TimeoutError("No user task appeared for the process instance.")


async def _wait_for_message_execution(
    client: FlowableClient, instance_id: str, attempts: int = 40, delay: float = 0.5
) -> str:
    """Poll until an execution is waiting on the spike message.

    Because the message catch event follows a timer, a non-empty result also confirms the timer
    fired.

    Args:
        client: The Flowable client.
        instance_id: The process instance identifier.
        attempts: Maximum number of polls.
        delay: Delay between polls, in seconds.

    Returns:
        The execution id waiting on the message.

    Raises:
        TimeoutError: If no waiting execution appears within the allotted attempts.
    """
    for _ in range(attempts):
        execution_id = await client.find_message_execution(instance_id, SPIKE_MESSAGE_NAME)
        if execution_id is not None:
            return execution_id
        await asyncio.sleep(delay)
    raise TimeoutError("Timer did not fire or message subscription never appeared.")


async def _wait_until_finished(
    client: FlowableClient, instance_id: str, attempts: int = 20, delay: float = 0.5
) -> bool:
    """Poll until the historic process instance reports an end time.

    Args:
        client: The Flowable client.
        instance_id: The process instance identifier.
        attempts: Maximum number of polls.
        delay: Delay between polls, in seconds.

    Returns:
        ``True`` once the instance has finished.

    Raises:
        TimeoutError: If the instance does not finish within the allotted attempts.
    """
    for _ in range(attempts):
        historic = await client.get_historic_process_instance(instance_id)
        if historic.get("endTime"):
            return True
        await asyncio.sleep(delay)
    raise TimeoutError("Process instance did not finish.")


async def run_spike(client: FlowableClient, business_key: str) -> SpikeResult:
    """Run the full spike cycle against an already-deployed spike process.

    Steps: idempotent start → claim and complete the user task → wait for the timer to fire →
    correlate the message → wait for completion → read history.

    Args:
        client: The Flowable client.
        business_key: The business key for the process instance.

    Returns:
        A summary including the recorded activity ids.
    """
    start = await start_process_idempotently(client, business_key)
    instance_id = start.instance_id

    task = await _wait_for_first_task(client, instance_id)
    task_id = str(task["id"])
    await client.claim_task(task_id, assignee="spike-user")
    await client.complete_task(task_id)

    execution_id = await _wait_for_message_execution(client, instance_id)
    await client.deliver_message(execution_id, SPIKE_MESSAGE_NAME)

    finished = await _wait_until_finished(client, instance_id)
    activities = await client.list_historic_activities(instance_id)
    activity_ids = [str(item["activityId"]) for item in activities]

    return SpikeResult(
        instance_id=instance_id,
        completed_task_id=task_id,
        finished=finished,
        activities=activity_ids,
    )

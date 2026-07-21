"""Integration tests for the Flowable spike (TASK_00D).

Exercise the full Process Adapter ↔ Flowable loop against a running Flowable instance:
deploy → idempotent start → user task claim/complete → timer → message correlation → history.

Skipped unless ``PA_FLOWABLE_BASE_URL`` is set (see conftest and `make spike`).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from process_adapter.application.spike import (
    SPIKE_PROCESS_KEY,
    run_spike,
    start_process_idempotently,
)
from process_adapter.infrastructure.flowable_client import FlowableClient

BPMN_PATH = Path(__file__).parent / "resources" / "spike_process.bpmn20.xml"

requires_flowable = pytest.mark.skipif(
    os.environ.get("PA_FLOWABLE_BASE_URL") is None,
    reason="Set PA_FLOWABLE_BASE_URL to run Flowable integration tests (see `make spike`).",
)


@requires_flowable
async def test_full_spike_cycle(flowable_client: FlowableClient) -> None:
    """The full loop runs and history records the user task, timer, message, and end."""
    await flowable_client.deploy_process("spike_process.bpmn20.xml", BPMN_PATH.read_bytes())
    business_key = f"spike-{uuid.uuid4().hex}"

    result = await run_spike(flowable_client, business_key)

    assert result.finished is True
    for activity_id in ("spikeUserTask", "spikeTimer", "spikeMessage", "end"):
        assert activity_id in result.activities, f"missing activity {activity_id}"


@requires_flowable
async def test_start_is_idempotent_by_business_key(flowable_client: FlowableClient) -> None:
    """Starting twice with the same business key reuses the same process instance."""
    await flowable_client.deploy_process("spike_process.bpmn20.xml", BPMN_PATH.read_bytes())
    business_key = f"spike-{uuid.uuid4().hex}"

    first = await start_process_idempotently(flowable_client, business_key, SPIKE_PROCESS_KEY)
    second = await start_process_idempotently(flowable_client, business_key, SPIKE_PROCESS_KEY)

    assert first.created is True
    assert second.created is False
    assert first.instance_id == second.instance_id

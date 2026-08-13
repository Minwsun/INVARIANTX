from __future__ import annotations

import asyncio
import hmac
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import Field

from app.domain.adapter import DomainAdapter
from app.domain.logistics_tools import LogisticsAdapter
from app.invariant.models import (
    FrozenModel,
    GateStatus,
    IntentContract,
)
from app.runtime.agents import AgentNodes, ModelExecutionBlocked
from app.runtime.events import EventJournal, EventType, RunStatus
from app.runtime.workflow import WorkflowRequest, WorkflowResult, build_invariant_workflow
from app.storage.memory import InMemoryStore


class RunSnapshot(FrozenModel):
    run_id: str
    status: RunStatus
    goal: str
    scenario: str = "standard"
    contract_id: str | None = None
    contract_version: int | None = None
    repair_count: int = 0
    llm_call_count: int = 0
    result: Any = None
    error: str | None = None


@dataclass
class _RunRecord:
    snapshot: RunSnapshot
    request: WorkflowRequest
    contract: IntentContract | None = None
    task: asyncio.Task[None] | None = None


class RunService:
    def __init__(
        self,
        store=None,
        journal: EventJournal | None = None,
        agent_nodes: AgentNodes | None = None,
        adapter: DomainAdapter | None = None,
    ) -> None:
        self.store = store or InMemoryStore()
        self.journal = journal or EventJournal(self.store)
        self.agent_nodes = agent_nodes
        self.adapter = adapter or LogisticsAdapter()
        self._runs: dict[str, _RunRecord] = {}

    async def create(
        self,
        goal: str,
        *,
        scenario: str = "standard",
    ) -> RunSnapshot:
        if self.agent_nodes is None and not os.getenv("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY is required for real agent execution")
        run_id = f"run_{uuid4().hex}"
        request = WorkflowRequest(
            run_id=run_id,
            goal=goal,
            scenario=scenario,
            state=self.adapter.baseline_state(),
        )
        snapshot = RunSnapshot(
            run_id=run_id,
            status=RunStatus.CREATED,
            goal=goal,
            scenario=scenario,
        )
        record = _RunRecord(snapshot=snapshot, request=request)
        self._runs[run_id] = record
        await self._save_snapshot(record)
        await self.journal.append(run_id, EventType.RUN_CREATED, "api")
        record.task = asyncio.create_task(self._execute(record))
        return snapshot

    async def get(self, run_id: str) -> RunSnapshot:
        record = self._runs.get(run_id)
        if record is not None:
            return record.snapshot
        stored = await self.store.get_run(run_id)
        if stored is None:
            raise KeyError(f"run {run_id} not found")
        return RunSnapshot.model_validate(stored)

    async def contract(self, run_id: str):
        record = self._runs.get(run_id)
        if record is not None and record.contract is not None:
            return record.contract
        snapshot = await self.get(run_id)
        if snapshot.contract_id is None or snapshot.contract_version is None:
            raise KeyError(f"contract for run {run_id} not found")
        stored = await self.store.get_contract(
            snapshot.contract_id,
            snapshot.contract_version,
        )
        if stored is None:
            raise KeyError(f"contract for run {run_id} not found")
        return IntentContract.model_validate(stored)

    async def cancel(self, run_id: str) -> bool:
        record = self._record(run_id)
        if record.snapshot.status in {
            RunStatus.COMPLETED,
            RunStatus.BLOCKED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return False
        await self.journal.append(run_id, EventType.RUN_CANCEL_REQUESTED, "api")
        if record.task is not None:
            record.task.cancel()
        return True

    async def _execute(self, record: _RunRecord) -> None:
        run_id = record.snapshot.run_id
        async def persist_action_decision(verdict):
            event_type = (
                EventType.GATE_PASSED
                if verdict.status == GateStatus.PASS
                else EventType.ACTION_BLOCKED
            )
            await self.journal.append(
                run_id,
                event_type,
                "check_action",
                {"status": verdict.status.value},
            )

        async def persist_contract(contract: IntentContract) -> None:
            await self.store.create_contract(contract)
            record.contract = contract
            record.snapshot = record.snapshot.model_copy(
                update={
                    "contract_id": contract.id,
                    "contract_version": contract.version,
                }
            )
            await self._save_snapshot(record)

        workflow = build_invariant_workflow(
            self.adapter.tools(),
            domain_vocabulary=self.adapter.vocabulary(),
            domain_adapter_name=self.adapter.name,
            intent_normalizer=self.adapter.normalize_intent,
            receipt_builder=self.adapter.build_receipt,
            action_decision_sink=persist_action_decision,
            contract_sink=persist_contract,
            agent_nodes=self.agent_nodes,
        )
        runner = InMemoryRunner(node=workflow, app_name="invariant")
        try:
            record.snapshot = record.snapshot.model_copy(
                update={"status": RunStatus.RUNNING}
            )
            await self._save_snapshot(record)
            await self.journal.append(run_id, EventType.RUN_STARTED, "runtime")
            await runner.session_service.create_session(
                app_name="invariant",
                user_id="runtime",
                session_id=run_id,
            )
            result = None
            async for event in runner.run_async(
                user_id="runtime",
                session_id=run_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=record.request.model_dump_json())],
                ),
            ):
                await self._publish_adk_event(record, event)
                if event.node_info and event.node_info.path.endswith("finalize@1"):
                    result = WorkflowResult.model_validate(event.output)
            if result is None:
                raise RuntimeError("workflow completed without final result")
            status = (
                RunStatus.COMPLETED
                if result.status == "COMPLETED"
                else RunStatus.BLOCKED
            )
            record.snapshot = record.snapshot.model_copy(
                update={
                    "status": status,
                    "repair_count": result.repair_count,
                    "llm_call_count": result.llm_call_count,
                    "result": result.model_dump(mode="json"),
                }
            )
            await self._save_snapshot(record)
            await self.journal.append(
                run_id,
                EventType.RUN_COMPLETED,
                "runtime",
                {"status": status.value},
            )
        except asyncio.CancelledError:
            record.snapshot = record.snapshot.model_copy(
                update={"status": RunStatus.CANCELLED}
            )
            await self._save_snapshot(record)
            await self.journal.append(run_id, EventType.RUN_CANCELLED, "runtime")
        except ModelExecutionBlocked as error:
            record.snapshot = record.snapshot.model_copy(
                update={"status": RunStatus.BLOCKED, "error": str(error)}
            )
            await self._save_snapshot(record)
            await self.journal.append(
                run_id,
                EventType.MODEL_FAILED,
                "runtime",
                {"error": str(error)},
            )
            await self.journal.append(
                run_id,
                EventType.RUN_COMPLETED,
                "runtime",
                {"status": RunStatus.BLOCKED.value},
            )
        except Exception as error:
            record.snapshot = record.snapshot.model_copy(
                update={"status": RunStatus.FAILED, "error": str(error)}
            )
            await self._save_snapshot(record)
            await self.journal.append(
                run_id,
                EventType.RUN_FAILED,
                "runtime",
                {"error": str(error)},
            )

    async def _publish_adk_event(self, record: _RunRecord, event) -> None:
        if not event.node_info:
            return
        run_id = record.snapshot.run_id
        node_name = event.node_info.path.rsplit("/", 1)[-1].split("@", 1)[0]
        route = event.actions.route
        mapping = {
            "intent_compiler": EventType.INTENT_COMPILED,
            "register_contract": EventType.CONTRACT_REGISTERED,
            "planner_agent": EventType.TASK_PROPOSED,
            "inject_demo_drift": EventType.DEMO_DRIFT_INJECTED,
            "repair_task": EventType.REPAIR_ACCEPTED,
            "worker_agent": EventType.ACTION_PROPOSED,
            "execute_tool": EventType.TOOL_COMPLETED,
            "validate_result": EventType.VALIDATION_COMPLETED,
        }
        event_type = mapping.get(node_name)
        if (
            node_name == "inject_demo_drift"
            and record.snapshot.scenario != "deliberate_constraint_omission"
        ):
            event_type = None
        if node_name == "check_delegation":
            if route == GateStatus.REPAIR.value:
                event_type = EventType.DRIFT_DETECTED
            elif route == GateStatus.ESCALATE.value:
                event_type = EventType.POLICY_ESCALATED
            elif route == GateStatus.PASS.value:
                event_type = EventType.GATE_PASSED
            else:
                event_type = EventType.ACTION_BLOCKED
        if event_type is not None:
            payload = {"route": route} if route else {}
            packet = _event_packet(event.output)
            if node_name == "inject_demo_drift" and packet and packet.contract:
                payload = {
                    "scenario": record.snapshot.scenario,
                    "removed_constraint_ids": [packet.contract.hard_constraints[0].id],
                }
            elif node_name == "check_delegation" and packet:
                payload.update(
                    {
                        "violation_ids": [
                            violation.reference_id for violation in packet.violations
                        ],
                        "drift_types": [
                            violation.drift_type.value for violation in packet.violations
                        ],
                    }
                )
            elif node_name == "repair_task" and packet and packet.delegation:
                payload["restored_constraint_ids"] = [
                    claim.constraint_id for claim in packet.delegation.constraint_claims
                ]
            elif node_name == "execute_tool" and packet:
                receipt = packet.tool_result
                if getattr(receipt, "status", None) == "unknown":
                    event_type = EventType.TOOL_TIMED_OUT
            elif node_name == "validate_result" and packet and packet.validation:
                if packet.validation.verdict == "BLOCK":
                    event_type = EventType.RECEIPT_REJECTED
            if packet and node_name in {"intent_compiler", "planner_agent", "worker_agent"}:
                role = {
                    "intent_compiler": "intent_compiler",
                    "planner_agent": "planner",
                    "worker_agent": "worker",
                }[node_name]
                failures = [
                    call.model_dump(mode="json")
                    for call in packet.model_calls
                    if call.outcome == "FAILED" and call.role == role
                ]
                for failure in failures:
                    await self.journal.append(
                        run_id,
                        EventType.MODEL_RETRY,
                        node_name,
                        failure,
                    )
            await self.journal.append(
                run_id,
                event_type,
                node_name,
                payload,
            )

    def _record(self, run_id: str) -> _RunRecord:
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise KeyError(f"run {run_id} not found") from error

    async def _save_snapshot(self, record: _RunRecord) -> None:
        await self.store.save_run(
            record.snapshot.run_id,
            record.snapshot.model_dump(mode="json"),
        )


def demo_key_matches(provided: str | None) -> bool:
    expected = os.getenv("INVARIANT_DEMO_KEY")
    return bool(expected and provided and hmac.compare_digest(provided, expected))


def _event_packet(output: Any) -> WorkflowResult | Any:
    try:
        from app.runtime.workflow import WorkflowPacket

        return WorkflowPacket.model_validate(output)
    except Exception:
        return None

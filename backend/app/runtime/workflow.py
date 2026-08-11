from __future__ import annotations

from typing import Any, Literal

from google.adk import Event, Workflow
from google.adk.agents.context import Context
from google.adk.workflow import START
from google.genai import types
from pydantic import Field

from app.invariant.action_gate import ActionGate
from app.invariant.gate import DelegationGate
from app.invariant.models import (
    ActionApproval,
    ActionProposal,
    DelegationProposal,
    DriftType,
    FrozenModel,
    GateVerdict,
    GateStatus,
    IntentContract,
    Violation,
)
from app.invariant.repair import repair_delegation
from app.invariant.semantic import ModelCallRecord, SemanticVerifier
from app.invariant.tools import ToolExecutionBlocked, ToolExecutor


class WorkflowRequest(FrozenModel):
    run_id: str = Field(min_length=1)
    contract: IntentContract
    planner_output: DelegationProposal
    worker_output: ActionProposal
    state: dict[str, float]


class WorkflowPacket(FrozenModel):
    request: WorkflowRequest
    delegation: DelegationProposal | None = None
    action: ActionProposal | None = None
    approval: ActionApproval | None = None
    violations: tuple[Violation, ...] = ()
    repair_count: int = 0
    llm_call_count: int = 0
    model_calls: tuple[ModelCallRecord, ...] = ()
    tool_result: Any = None
    status: Literal["RUNNING", "BLOCKED", "COMPLETED"] = "RUNNING"


class WorkflowResult(FrozenModel):
    run_id: str
    status: Literal["BLOCKED", "COMPLETED"]
    repair_count: int
    llm_call_count: int
    violations: tuple[Violation, ...]
    model_calls: tuple[ModelCallRecord, ...]
    tool_result: Any = None


def build_invariant_workflow(
    tools: dict[str, tuple[Any, Any]],
    *,
    max_repairs: int = 2,
    max_llm_calls: int = 5,
    semantic_verifier: SemanticVerifier | None = None,
) -> Workflow:
    if not 1 <= max_llm_calls <= 5:
        raise ValueError("max_llm_calls must be between 1 and 5")
    if max_repairs < 0:
        raise ValueError("max_repairs cannot be negative")
    delegation_gate = DelegationGate()
    action_gate = ActionGate()
    executor = ToolExecutor(action_gate)
    for name, (tool, risk) in tools.items():
        executor.register(name, tool, risk)

    def parse_request(ctx: Context, node_input: types.Content) -> WorkflowPacket:
        if not node_input.parts or not node_input.parts[0].text:
            raise ValueError("workflow input must contain JSON text")
        request = WorkflowRequest.model_validate_json(node_input.parts[0].text)
        ctx.state["run_id"] = request.run_id
        ctx.state["contract_id"] = request.contract.id
        ctx.state["contract_version"] = request.contract.version
        ctx.state["repair_count"] = 0
        ctx.state["llm_call_count"] = 0
        return WorkflowPacket(request=request)

    def planner_agent(node_input: WorkflowPacket) -> WorkflowPacket:
        return node_input.model_copy(
            update={"delegation": node_input.request.planner_output}
        )

    async def check_delegation(ctx: Context, node_input: WorkflowPacket) -> Event:
        if node_input.delegation is None:
            return Event(
                output=node_input.model_copy(update={"status": "BLOCKED"}),
                route=GateStatus.BLOCK.value,
            )
        verdict = delegation_gate.check(
            node_input.request.contract,
            node_input.delegation,
        )
        route = verdict.status
        if any(
            violation.drift_type
            in {DriftType.OBJECTIVE_SUBSTITUTION, DriftType.STALE_CONTRACT}
            for violation in verdict.violations
        ):
            route = GateStatus.BLOCK
        packet = node_input.model_copy(update={"violations": verdict.violations})
        if route == GateStatus.BLOCK:
            packet = packet.model_copy(update={"status": "BLOCKED"})
        if route == GateStatus.PASS and node_input.request.contract.semantic_constraints:
            if semantic_verifier is None:
                violation = Violation(
                    drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                    reference_id="semantic_verifier",
                    evidence="semantic constraints require a configured verifier",
                )
                return Event(
                    output=packet.model_copy(
                        update={"status": "BLOCKED", "violations": (violation,)}
                    ),
                    route=GateStatus.BLOCK.value,
                )
            try:
                semantic_result = await semantic_verifier.verify(
                    node_input.delegation,
                    node_input.request.contract.semantic_constraints,
                    remaining_calls=max_llm_calls - node_input.llm_call_count,
                )
            except RuntimeError as error:
                violation = Violation(
                    drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                    reference_id="llm_budget",
                    evidence=str(error),
                )
                return Event(
                    output=packet.model_copy(
                        update={"status": "BLOCKED", "violations": (violation,)}
                    ),
                    route=GateStatus.BLOCK.value,
                )
            llm_call_count = node_input.llm_call_count + len(semantic_result.calls)
            ctx.state["llm_call_count"] = llm_call_count
            packet = packet.model_copy(
                update={
                    "llm_call_count": llm_call_count,
                    "model_calls": (*node_input.model_calls, *semantic_result.calls),
                }
            )
            semantic_verdict = semantic_result.verdict
            if semantic_verdict.uncertain:
                violation = Violation(
                    drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                    reference_id="semantic_verifier",
                    evidence=semantic_verdict.evidence,
                )
                return Event(
                    output=packet.model_copy(
                        update={"status": "BLOCKED", "violations": (violation,)}
                    ),
                    route=GateStatus.BLOCK.value,
                )
            if not semantic_verdict.preserved:
                violation_ids = semantic_verdict.violation_ids or tuple(
                    constraint.id
                    for constraint in node_input.request.contract.semantic_constraints
                )
                violations = tuple(
                    Violation(
                        drift_type=DriftType.CONTRADICTION,
                        reference_id=constraint_id,
                        evidence=semantic_verdict.evidence,
                    )
                    for constraint_id in violation_ids
                )
                return Event(
                    output=packet.model_copy(update={"violations": violations}),
                    route=GateStatus.REPAIR.value,
                )
        return Event(output=packet, route=route.value)

    def repair_task(ctx: Context, node_input: WorkflowPacket) -> Event:
        if node_input.repair_count >= max_repairs or node_input.delegation is None:
            return Event(
                output=node_input.model_copy(update={"status": "BLOCKED"}),
                route=GateStatus.BLOCK.value,
            )
        verdict = (
            GateVerdict(status=GateStatus.REPAIR, violations=node_input.violations)
            if node_input.violations
            else delegation_gate.check(
                node_input.request.contract,
                node_input.delegation,
            )
        )
        repair = repair_delegation(
            node_input.request.contract,
            node_input.delegation,
            verdict,
        )
        repair_count = node_input.repair_count + 1
        ctx.state["repair_count"] = repair_count
        return Event(
            output=node_input.model_copy(
                update={
                    "delegation": repair.repaired,
                    "repair_count": repair_count,
                    "violations": (),
                }
            ),
            route="RECHECK",
        )

    def worker_agent(node_input: WorkflowPacket) -> WorkflowPacket:
        return node_input.model_copy(update={"action": node_input.request.worker_output})

    def check_action(node_input: WorkflowPacket) -> Event:
        if node_input.action is None:
            return Event(
                output=node_input.model_copy(update={"status": "BLOCKED"}),
                route=GateStatus.BLOCK.value,
            )
        result = action_gate.check(
            node_input.request.contract,
            node_input.action,
            node_input.request.state,
        )
        packet = node_input.model_copy(
            update={
                "approval": result.approval,
                "violations": result.verdict.violations,
            }
        )
        if result.verdict.status != GateStatus.PASS:
            packet = packet.model_copy(update={"status": "BLOCKED"})
        return Event(output=packet, route=result.verdict.status.value)

    def execute_tool(node_input: WorkflowPacket) -> WorkflowPacket:
        if node_input.action is None:
            return node_input.model_copy(update={"status": "BLOCKED"})
        try:
            result = executor.execute(
                contract=node_input.request.contract,
                proposal=node_input.action,
                approval=node_input.approval,
                state=node_input.request.state,
            )
        except ToolExecutionBlocked as error:
            return node_input.model_copy(
                update={
                    "status": "BLOCKED",
                    "violations": (
                        Violation(
                            drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                            reference_id=node_input.action.action_id,
                            evidence=str(error),
                        ),
                    ),
                }
            )
        return node_input.model_copy(update={"tool_result": result})

    def validate_result(node_input: WorkflowPacket) -> WorkflowPacket:
        status = "COMPLETED" if node_input.tool_result is not None else "BLOCKED"
        return node_input.model_copy(update={"status": status})

    def finalize(node_input: WorkflowPacket) -> WorkflowResult:
        status = "COMPLETED" if node_input.status == "COMPLETED" else "BLOCKED"
        return WorkflowResult(
            run_id=node_input.request.run_id,
            status=status,
            repair_count=node_input.repair_count,
            llm_call_count=node_input.llm_call_count,
            violations=node_input.violations,
            model_calls=node_input.model_calls,
            tool_result=node_input.tool_result,
        )

    return Workflow(
        name="invariant_workflow",
        edges=[
            (START, parse_request, planner_agent, check_delegation),
            (
                check_delegation,
                {
                    GateStatus.PASS.value: worker_agent,
                    GateStatus.REPAIR.value: repair_task,
                    GateStatus.BLOCK.value: finalize,
                },
            ),
            (
                repair_task,
                {
                    "RECHECK": check_delegation,
                    GateStatus.BLOCK.value: finalize,
                },
            ),
            (worker_agent, check_action),
            (
                check_action,
                {
                    GateStatus.PASS.value: execute_tool,
                    GateStatus.BLOCK.value: finalize,
                },
            ),
            (execute_tool, validate_result, finalize),
        ],
    )

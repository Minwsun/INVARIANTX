from __future__ import annotations

from collections.abc import Awaitable, Callable
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
    ExecutionReceipt,
    FrozenModel,
    GateVerdict,
    GateStatus,
    IntentContract,
    IntentContractCandidate,
    RawIntentContractCandidate,
    Permission,
    ToolRisk,
    ValidationResult,
    Violation,
)
from app.invariant.repair import repair_delegation
from app.invariant.semantic import ModelCallRecord, SemanticVerifier
from app.invariant.tools import ToolExecutionBlocked, ToolExecutor
from app.runtime.agents import AgentNodes, DEFAULT_MODEL, build_agent_nodes


class WorkflowRequest(FrozenModel):
    run_id: str = Field(min_length=1)
    goal: str = Field(min_length=1, max_length=4000)
    state: dict[str, float]
    scenario: Literal["standard", "deliberate_constraint_omission"] = "standard"


class WorkflowPacket(FrozenModel):
    request: WorkflowRequest
    contract: IntentContract | None = None
    delegation: DelegationProposal | None = None
    action: ActionProposal | None = None
    approval: ActionApproval | None = None
    violations: tuple[Violation, ...] = ()
    repair_count: int = 0
    llm_call_count: int = 0
    model_calls: tuple[ModelCallRecord, ...] = ()
    tool_result: Any = None
    validation: ValidationResult | None = None
    status: Literal["RUNNING", "BLOCKED", "COMPLETED"] = "RUNNING"


class WorkflowResult(FrozenModel):
    run_id: str
    status: Literal["BLOCKED", "COMPLETED"]
    repair_count: int
    llm_call_count: int
    violations: tuple[Violation, ...]
    model_calls: tuple[ModelCallRecord, ...]
    tool_result: Any = None
    validation: ValidationResult | None = None


def build_invariant_workflow(
    tools: dict[str, tuple[Any, Any]],
    *,
    max_repairs: int = 2,
    max_llm_calls: int = 5,
    semantic_verifier: SemanticVerifier | None = None,
    action_decision_sink: Callable[[GateVerdict], Awaitable[None]] | None = None,
    contract_sink: Callable[[IntentContract], Awaitable[None]] | None = None,
    agent_nodes: AgentNodes | None = None,
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
    nodes = agent_nodes or build_agent_nodes()
    runtime_permissions = tuple(
        Permission(tool_name=name, risk=risk) for name, (_, risk) in tools.items()
    )

    def parse_request(ctx: Context, node_input: types.Content) -> WorkflowPacket:
        if not node_input.parts or not node_input.parts[0].text:
            raise ValueError("workflow input must contain JSON text")
        request = WorkflowRequest.model_validate_json(node_input.parts[0].text)
        ctx.state["run_id"] = request.run_id
        ctx.state["repair_count"] = 0
        ctx.state["llm_call_count"] = 0
        return WorkflowPacket(request=request)

    def prepare_intent(node_input: WorkflowPacket) -> dict[str, Any]:
        return {
            "goal": node_input.request.goal,
            "domain_vocabulary": {
                "objectives": ["logistics_cost"],
                "subjects": ["medical_orders"],
                "metrics": ["delivery_delay"],
                "references": list(node_input.request.state),
            },
        }

    async def register_contract(
        ctx: Context,
        node_input: Any,
    ) -> WorkflowPacket:
        request = WorkflowRequest.model_validate(ctx.state["workflow_request"])
        raw_candidate = RawIntentContractCandidate.model_validate(
            _json_compatible(node_input)
        )
        candidate = IntentContractCandidate.model_validate(
            _normalize_intent_candidate(
                raw_candidate.model_dump(mode="json"),
                request.state,
            )
        )
        contract = IntentContract(
            id=f"intent_{request.run_id}",
            version=1,
            original_request=request.goal,
            objectives=candidate.objectives,
            hard_constraints=candidate.hard_constraints,
            protected_entities=candidate.protected_entities,
            forbidden_outcomes=candidate.forbidden_outcomes,
            permissions=runtime_permissions,
            semantic_constraints=candidate.semantic_constraints,
        )
        if contract_sink is not None:
            await contract_sink(contract)
        ctx.state["contract_id"] = contract.id
        ctx.state["contract_version"] = contract.version
        return _attach_agent_telemetry(
            ctx,
            WorkflowPacket(
                request=request,
                contract=contract,
                llm_call_count=int(ctx.state["llm_call_count"]),
            ),
            "intent_compiler",
        )

    def prepare_planner(node_input: WorkflowPacket) -> dict[str, Any]:
        if node_input.contract is None:
            raise RuntimeError("intent contract is not registered")
        return {
            "run_id": node_input.request.run_id,
            "contract": node_input.contract.model_dump(mode="json"),
            "available_tools": [permission.tool_name for permission in runtime_permissions],
            "state": node_input.request.state,
        }

    def merge_planner(ctx: Context, node_input: Any) -> WorkflowPacket:
        packet = WorkflowPacket.model_validate(ctx.state["workflow_packet"])
        proposal = DelegationProposal.model_validate(node_input)
        return _attach_agent_telemetry(
            ctx,
            packet.model_copy(update={"delegation": proposal}),
            "planner_agent",
        )

    def inject_demo_drift(node_input: WorkflowPacket) -> WorkflowPacket:
        if (
            node_input.request.scenario != "deliberate_constraint_omission"
            or node_input.contract is None
            or node_input.delegation is None
            or not node_input.contract.hard_constraints
        ):
            return node_input
        target_id = node_input.contract.hard_constraints[0].id
        claims = tuple(
            claim
            for claim in node_input.delegation.constraint_claims
            if claim.constraint_id != target_id
        )
        return node_input.model_copy(
            update={
                "delegation": node_input.delegation.model_copy(
                    update={"constraint_claims": claims}
                )
            }
        )

    async def check_delegation(ctx: Context, node_input: WorkflowPacket) -> Event:
        if node_input.delegation is None:
            return Event(
                output=node_input.model_copy(update={"status": "BLOCKED"}),
                route=GateStatus.BLOCK.value,
            )
        verdict = delegation_gate.check(
            node_input.contract,
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
        if route == GateStatus.PASS and node_input.contract.semantic_constraints:
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
                    node_input.contract.semantic_constraints,
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
                    for constraint in node_input.contract.semantic_constraints
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
                node_input.contract,
                node_input.delegation,
            )
        )
        repair = repair_delegation(
            node_input.contract,
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

    def prepare_worker(ctx: Context, node_input: WorkflowPacket) -> dict[str, Any]:
        if node_input.contract is None or node_input.delegation is None:
            raise RuntimeError("worker requires passed delegation and contract")
        ctx.state["workflow_packet"] = node_input.model_dump(mode="json")
        return {
            "delegation": node_input.delegation.model_dump(mode="json"),
            "contract": node_input.contract.model_dump(mode="json"),
            "allowed_tools": [
                permission.model_dump(mode="json")
                for permission in node_input.contract.permissions
            ],
            "state": node_input.request.state,
        }

    def merge_worker(ctx: Context, node_input: Any) -> WorkflowPacket:
        packet = WorkflowPacket.model_validate(ctx.state["workflow_packet"])
        action = ActionProposal.model_validate(node_input)
        return _attach_agent_telemetry(
            ctx,
            packet.model_copy(update={"action": action}),
            "worker_agent",
        )

    async def check_action(node_input: WorkflowPacket) -> Event:
        if node_input.action is None:
            return Event(
                output=node_input.model_copy(update={"status": "BLOCKED"}),
                route=GateStatus.BLOCK.value,
            )
        result = action_gate.check(
            node_input.contract,
            node_input.action,
            node_input.request.state,
        )
        if action_decision_sink is not None:
            await action_decision_sink(result.verdict)
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
                contract=node_input.contract,
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
        validation = _validate_execution(node_input)
        return node_input.model_copy(
            update={
                "status": "COMPLETED" if validation.verdict == "PASS" else "BLOCKED",
                "validation": validation,
                "violations": validation.violations,
            }
        )

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
            validation=node_input.validation,
        )

    def remember_request(ctx: Context, node_input: WorkflowPacket) -> WorkflowPacket:
        ctx.state["workflow_request"] = node_input.request.model_dump(mode="json")
        return node_input

    def remember_packet(ctx: Context, node_input: WorkflowPacket) -> WorkflowPacket:
        ctx.state["workflow_packet"] = node_input.model_dump(mode="json")
        return node_input

    def reserve_agent_call(
        ctx: Context,
        node_input: WorkflowPacket,
    ) -> WorkflowPacket:
        if node_input.llm_call_count >= max_llm_calls:
            raise RuntimeError("LLM call budget exhausted")
        packet = node_input.model_copy(
            update={"llm_call_count": node_input.llm_call_count + 1}
        )
        ctx.state["llm_call_count"] = packet.llm_call_count
        ctx.state["workflow_packet"] = packet.model_dump(mode="json")
        return packet

    def reserve_compiler_call(ctx: Context, node_input: WorkflowPacket) -> WorkflowPacket:
        return reserve_agent_call(ctx, node_input)

    def reserve_planner_call(ctx: Context, node_input: WorkflowPacket) -> WorkflowPacket:
        return reserve_agent_call(ctx, node_input)

    def reserve_worker_call(ctx: Context, node_input: WorkflowPacket) -> WorkflowPacket:
        return reserve_agent_call(ctx, node_input)

    def _attach_agent_telemetry(
        ctx: Context,
        packet: WorkflowPacket,
        agent_name: str,
    ) -> WorkflowPacket:
        telemetry = ctx.state.get(f"model_call.{agent_name}") or {
            "model": DEFAULT_MODEL
        }
        return packet.model_copy(
            update={
                "model_calls": (
                    *packet.model_calls,
                    ModelCallRecord.model_validate(telemetry),
                ),
            }
        )

    return Workflow(
        name="invariant_workflow",
        edges=[
            (
                START,
                parse_request,
                remember_request,
                reserve_compiler_call,
                prepare_intent,
                nodes.intent_compiler,
                register_contract,
                remember_packet,
                reserve_planner_call,
                prepare_planner,
                nodes.planner,
                merge_planner,
                inject_demo_drift,
                check_delegation,
            ),
            (
                check_delegation,
                {
                    GateStatus.PASS.value: reserve_worker_call,
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
            (reserve_worker_call, prepare_worker, nodes.worker, merge_worker, check_action),
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


def _normalize_intent_candidate(
    candidate: Any,
    state: dict[str, float],
) -> Any:
    if not isinstance(candidate, dict):
        return candidate
    normalized = {**candidate}
    objectives = []
    reduction_operators = {
        "decrease_by",
        "decrease_by_at_least",
        "decrease_by_percent",
        "decrease_by_percentage",
        "reduce_by",
        "reduce_by_percentage",
    }
    for objective in candidate.get("objectives", []):
        item = dict(objective)
        if item.get("operator") in reduction_operators:
            item["operator"] = "decrease_by"
        objectives.append(item)
    normalized["objectives"] = objectives
    constraints = []
    constraint_operators = {
        "less_than_or_equal": "less_than_or_equal",
        "less_than_or_equals": "less_than_or_equal",
        "at_most": "less_than_or_equal",
        "greater_than_or_equal": "greater_than_or_equal",
        "greater_than_or_equals": "greater_than_or_equal",
        "at_least": "greater_than_or_equal",
        "equal": "equal",
        "equals": "equal",
    }
    for constraint in candidate.get("hard_constraints", []):
        item = dict(constraint)
        operator = constraint_operators.get(str(item.get("operator", "")).casefold())
        if operator:
            item["operator"] = operator
        metric = item.get("metric")
        baseline_matches = [
            key for key in state if key.rsplit(".", 1)[-1] == metric
        ]
        source_span = str(item.get("source_span", "")).lower()
        if (
            not baseline_matches
            and "delay" in source_span
            and "baseline.delivery_delay" in state
        ):
            item["metric"] = "delivery_delay"
            baseline_matches = ["baseline.delivery_delay"]
        if (
            item.get("operator") == "equal"
            and item.get("value") == 0
            and len(baseline_matches) == 1
            and any(term in source_span for term in ("without delay", "not delay"))
        ):
            item["operator"] = "less_than_or_equal"
            item["value"] = None
            item["value_ref"] = baseline_matches[0]
        if item.get("value") is None and not item.get("value_ref"):
            if len(baseline_matches) == 1:
                item["value_ref"] = baseline_matches[0]
        if item.get("value") is None:
            item.pop("value", None)
        if not item.get("value_ref"):
            item.pop("value_ref", None)
        constraints.append(item)
    normalized["hard_constraints"] = constraints
    return normalized


_ground_constraint_references = _normalize_intent_candidate


def _json_compatible(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _validate_execution(packet: WorkflowPacket) -> ValidationResult:
    if packet.contract is None:
        return _blocked_validation("contract", "intent contract is missing")
    try:
        receipt = ExecutionReceipt.model_validate(packet.tool_result)
    except Exception as error:
        return _blocked_validation("execution_receipt", f"invalid receipt: {error}")
    if receipt.status != "applied":
        return _blocked_validation(
            "execution_receipt",
            f"tool status is {receipt.status!r}, expected 'applied'",
        )

    violations: list[Violation] = []
    objective_status: dict[str, bool] = {}
    constraint_status: dict[str, bool] = {}

    for objective in packet.contract.objectives:
        actual = receipt.actual_metrics.get(objective.metric)
        reference_key = objective.reference
        if reference_key not in packet.request.state:
            reference_key = f"baseline.{objective.metric}"
        baseline = packet.request.state.get(reference_key)
        passed = (
            actual is not None
            and baseline is not None
            and _objective_holds(
                actual,
                baseline,
                objective.operator,
                objective.target,
                objective.unit,
            )
        )
        objective_status[objective.id] = passed
        if not passed:
            violations.append(
                Violation(
                    drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                    reference_id=objective.id,
                    evidence="actual metric missing or objective target not satisfied",
                )
            )

    for constraint in packet.contract.hard_constraints:
        actual = receipt.actual_metrics.get(constraint.metric)
        expected = (
            constraint.value
            if constraint.value is not None
            else packet.request.state.get(constraint.value_ref or "")
        )
        passed = (
            actual is not None
            and expected is not None
            and _constraint_holds(actual, expected, constraint.operator.value)
        )
        constraint_status[constraint.id] = passed
        if not passed:
            violations.append(
                Violation(
                    drift_type=DriftType.CONTRADICTION,
                    reference_id=constraint.id,
                    evidence="actual metric missing or hard constraint violated",
                )
            )

    for outcome in packet.contract.forbidden_outcomes:
        if outcome in receipt.occurred_outcomes:
            violations.append(
                Violation(
                    drift_type=DriftType.CONTRADICTION,
                    reference_id=outcome,
                    evidence="forbidden outcome occurred",
                )
            )
    for entity in packet.contract.protected_entities:
        if receipt.protected_entities.get(entity) is not True:
            violations.append(
                Violation(
                    drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                    reference_id=entity,
                    evidence="protected entity preservation is missing or false",
                )
            )

    return ValidationResult(
        verdict="BLOCK" if violations else "PASS",
        objective_status=objective_status,
        constraint_status=constraint_status,
        violations=tuple(violations),
    )


def _blocked_validation(reference_id: str, evidence: str) -> ValidationResult:
    return ValidationResult(
        verdict="BLOCK",
        violations=(
            Violation(
                drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                reference_id=reference_id,
                evidence=evidence,
            ),
        ),
    )


def _objective_holds(
    actual: float,
    baseline: float,
    operator: str,
    target: float,
    unit: str,
) -> bool:
    if unit == "percent":
        target /= 100
    elif unit != "ratio":
        return False
    if operator == "decrease_by":
        return baseline != 0 and (baseline - actual) / baseline >= target
    if operator == "less_than_or_equal":
        return actual <= target
    if operator == "greater_than_or_equal":
        return actual >= target
    if operator == "equal":
        return actual == target
    return False


def _constraint_holds(actual: float, expected: float, operator: str) -> bool:
    if operator == "less_than_or_equal":
        return actual <= expected
    if operator == "greater_than_or_equal":
        return actual >= expected
    if operator == "equal":
        return actual == expected
    return False

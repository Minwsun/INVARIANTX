from datetime import datetime, timedelta, timezone

from app.domain.logistics import medical_logistics_contract
from app.domain.logistics_tools import LogisticsTools
from app.invariant.action_gate import ActionGate
from app.invariant.digest import canonical_digest
from app.invariant.models import (
    ActionProposal,
    DriftType,
    GateStatus,
    ToolRisk,
)
from app.invariant.tools import ToolExecutionBlocked, ToolExecutor


def action_proposal(
    *,
    medical_delay: float = 10,
    version: int = 1,
    plan_id: str = "plan-safe",
) -> ActionProposal:
    return ActionProposal(
        action_id="A-1",
        contract_id="I-001",
        contract_version=version,
        tool_name="apply_plan",
        risk=ToolRisk.SIDE_EFFECT,
        arguments={"plan_id": plan_id},
        proposed_metrics={"delivery_delay": medical_delay},
    )


def test_canonical_digest_ignores_object_key_order() -> None:
    assert canonical_digest({"b": 2, "a": 1}) == canonical_digest({"a": 1, "b": 2})


def test_safe_side_effect_receives_bound_approval() -> None:
    contract = medical_logistics_contract()
    state = {"baseline.medical_delay": 10}
    proposal = action_proposal()

    result = ActionGate().check(contract, proposal, state)

    assert result.verdict.status == GateStatus.PASS
    assert result.approval is not None
    assert result.approval.tool_name == "apply_plan"
    assert result.approval.arguments_digest == canonical_digest(proposal.arguments)


def test_medical_delay_increase_is_blocked() -> None:
    contract = medical_logistics_contract()

    result = ActionGate().check(
        contract,
        action_proposal(medical_delay=11),
        {"baseline.medical_delay": 10},
    )

    assert result.verdict.status == GateStatus.BLOCK
    assert result.verdict.violations[0].reference_id == "MEDICAL_SLA"
    assert result.approval is None


def test_missing_metric_evidence_is_blocked() -> None:
    proposal = action_proposal().model_copy(update={"proposed_metrics": {}})

    result = ActionGate().check(
        medical_logistics_contract(),
        proposal,
        {"baseline.medical_delay": 10},
    )

    assert result.verdict.violations[0].drift_type == DriftType.INSUFFICIENT_EVIDENCE


def test_mutated_arguments_are_rejected() -> None:
    contract = medical_logistics_contract()
    state = {"baseline.medical_delay": 10}
    gate = ActionGate()
    proposal = action_proposal()
    approval = gate.check(contract, proposal, state).approval
    mutated = action_proposal(plan_id="plan-unsafe")

    verdict = gate.verify_approval(contract, mutated, approval, state)

    assert verdict.status == GateStatus.BLOCK
    assert verdict.violations[0].drift_type == DriftType.ARGUMENT_MUTATION


def test_stale_contract_is_rejected() -> None:
    contract = medical_logistics_contract()

    result = ActionGate().check(
        contract,
        action_proposal(version=2),
        {"baseline.medical_delay": 10},
    )

    assert result.verdict.status == GateStatus.BLOCK
    assert result.verdict.violations[0].drift_type == DriftType.STALE_CONTRACT


def test_expired_approval_is_rejected() -> None:
    contract = medical_logistics_contract()
    state = {"baseline.medical_delay": 10}
    gate = ActionGate(approval_ttl=timedelta(seconds=10))
    proposal = action_proposal()
    issued_at = datetime(2026, 8, 11, tzinfo=timezone.utc)
    approval = gate.check(contract, proposal, state, now=issued_at).approval

    verdict = gate.verify_approval(
        contract,
        proposal,
        approval,
        state,
        now=issued_at + timedelta(seconds=10),
    )

    assert verdict.status == GateStatus.BLOCK
    assert verdict.violations[0].drift_type == DriftType.EXPIRED_APPROVAL


def test_executor_does_not_run_side_effect_without_approval() -> None:
    contract = medical_logistics_contract()
    tools = LogisticsTools()
    executor = ToolExecutor(ActionGate())
    executor.register("apply_plan", tools.apply_plan, ToolRisk.SIDE_EFFECT)

    try:
        executor.execute(
            contract,
            action_proposal(),
            approval=None,
            state={"baseline.medical_delay": 10},
        )
    except ToolExecutionBlocked:
        pass
    else:
        raise AssertionError("side effect executed without approval")

    assert tools.applied_plans == []


def test_executor_runs_exact_approved_side_effect() -> None:
    contract = medical_logistics_contract()
    state = {"baseline.medical_delay": 10}
    proposal = action_proposal()
    gate = ActionGate()
    approval = gate.check(contract, proposal, state).approval
    tools = LogisticsTools()
    executor = ToolExecutor(gate)
    executor.register("apply_plan", tools.apply_plan, ToolRisk.SIDE_EFFECT)

    result = executor.execute(contract, proposal, approval, state)

    assert result == {"status": "applied", "plan_id": "plan-safe"}
    assert tools.applied_plans == ["plan-safe"]


def test_executor_rejects_side_effect_risk_downgrade() -> None:
    contract = medical_logistics_contract()
    tools = LogisticsTools()
    executor = ToolExecutor(ActionGate())
    executor.register("apply_plan", tools.apply_plan, ToolRisk.SIDE_EFFECT)
    downgraded = action_proposal().model_copy(update={"risk": ToolRisk.READ_ONLY})

    try:
        executor.execute(
            contract,
            downgraded,
            approval=None,
            state={"baseline.medical_delay": 10},
        )
    except ToolExecutionBlocked:
        pass
    else:
        raise AssertionError("side effect executed after risk downgrade")

    assert tools.applied_plans == []

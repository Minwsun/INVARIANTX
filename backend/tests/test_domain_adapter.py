import pytest

from app.domain.logistics_tools import LogisticsAdapter
from app.domain.logistics import medical_logistics_contract
from app.invariant.action_gate import ActionGate
from app.invariant.models import ActionProposal, EvidenceType, ToolRisk


def test_logistics_adapter_builds_canonical_simulator_receipt() -> None:
    adapter = LogisticsAdapter()
    raw = adapter.runtime_tools.apply_plan("safe_balanced")

    receipt = adapter.build_receipt(raw, adapter.baseline_state())

    assert receipt.plan_id == "safe_balanced"
    assert receipt.evidence_source.type == EvidenceType.SIMULATOR
    assert receipt.evidence_source.adapter == "logistics-v1"


def test_logistics_adapter_rejects_malformed_result() -> None:
    with pytest.raises(ValueError):
        LogisticsAdapter().build_receipt({"status": "applied"}, {})


def test_logistics_adapter_selects_slow_tool_only_for_timeout_demo() -> None:
    adapter = LogisticsAdapter()

    standard_tool = adapter.tools()["apply_plan"][0]
    timeout_tool = adapter.tools("deliberate_tool_timeout")["apply_plan"][0]

    assert standard_tool.__name__ == "apply_plan"
    assert timeout_tool.__name__ == "apply_plan_slow"


def test_logistics_adapter_projects_metrics_independently_of_worker_claims() -> None:
    adapter = LogisticsAdapter()
    proposal = ActionProposal(
        action_id="A-1",
        contract_id="I-1",
        contract_version=1,
        tool_name="apply_plan",
        risk=ToolRisk.SIDE_EFFECT,
        arguments={"plan_id": "cheapest"},
        proposed_metrics={"delivery_delay": 1},
    )

    projected = adapter.project_action(proposal)

    assert projected.proposed_metrics["delivery_delay"] == 12
    assert projected.proposed_metrics["logistics_cost"] == 800


def test_action_gate_uses_simulator_projection_to_block_unsafe_plan() -> None:
    adapter = LogisticsAdapter()
    proposal = ActionProposal(
        action_id="A-1",
        contract_id="I-001",
        contract_version=1,
        tool_name="apply_plan",
        risk=ToolRisk.SIDE_EFFECT,
        arguments={"plan_id": "cheapest"},
        proposed_metrics={"delivery_delay": 1},
    )

    result = ActionGate().check(
        medical_logistics_contract(),
        adapter.project_action(proposal),
        {"baseline.medical_delay": 10},
    )

    assert result.verdict.status == "BLOCK"
    assert result.approval is None


def test_logistics_adapter_repairs_unsafe_plan_deterministically() -> None:
    adapter = LogisticsAdapter()
    unsafe = ActionProposal(
        action_id="A-1",
        contract_id="I-001",
        contract_version=1,
        tool_name="apply_plan",
        risk=ToolRisk.SIDE_EFFECT,
        arguments={"plan_id": "cheapest"},
        proposed_metrics={},
    )

    repaired = adapter.repair_action(unsafe)

    assert repaired is not None
    assert repaired.arguments == {"plan_id": "safe_balanced"}
    assert repaired.proposed_metrics["delivery_delay"] == 9

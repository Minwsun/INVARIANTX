import pytest

from app.domain.logistics_tools import LogisticsAdapter
from app.invariant.models import EvidenceType


def test_logistics_adapter_builds_canonical_simulator_receipt() -> None:
    adapter = LogisticsAdapter()
    raw = adapter.runtime_tools.apply_plan("plan-1")

    receipt = adapter.build_receipt(raw, adapter.baseline_state())

    assert receipt.plan_id == "plan-1"
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

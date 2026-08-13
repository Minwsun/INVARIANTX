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

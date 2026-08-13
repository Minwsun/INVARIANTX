import pytest

from app.domain.procurement_simulator import ProcurementSimulator
from app.domain.procurement_tools import ProcurementAdapter
from app.invariant.models import Constraint, IntentContract, Objective, Permission, ToolRisk
from app.runtime.workflow import validate_execution


def procurement_contract() -> IntentContract:
    return IntentContract(
        id="PROC-1",
        version=1,
        original_request="Reduce procurement cost by 12% without blocked suppliers; critical parts within 7 days.",
        objectives=(Objective(id="OBJ-1", metric="procurement_cost", operator="decrease_by", target=12, unit="percent", reference="baseline", source_span="Reduce procurement cost by 12%"),),
        hard_constraints=(
            Constraint(id="SUPPLIER", subject="suppliers", metric="blocked_suppliers_used", operator="equal", value=0, source_span="without blocked suppliers"),
            Constraint(id="DELIVERY", subject="critical_components", metric="critical_delivery_days", operator="less_than_or_equal", value=7, source_span="within 7 days"),
        ),
        protected_entities=("critical_components",),
        forbidden_outcomes=("use_blocked_supplier",),
        permissions=(Permission(tool_name="apply_procurement_plan", risk=ToolRisk.SIDE_EFFECT),),
    )


def test_procurement_simulator_is_deterministic_and_fail_closed() -> None:
    simulator = ProcurementSimulator()
    assert simulator.execute("safe_balanced") == simulator.execute("safe_balanced")
    assert len(simulator.execute("safe_balanced")["assignments_digest"]) == 64
    with pytest.raises(ValueError, match="unknown procurement plan"):
        simulator.execute("invented")


def test_same_validator_blocks_unsafe_and_passes_safe_procurement() -> None:
    adapter = ProcurementAdapter()
    contract = procurement_contract()
    unsafe = adapter.build_receipt(adapter.simulator.execute("cheapest"), adapter.baseline_state())
    safe = adapter.build_receipt(adapter.simulator.execute("safe_balanced"), adapter.baseline_state())

    assert validate_execution(contract, adapter.baseline_state(), unsafe).verdict == "BLOCK"
    assert validate_execution(contract, adapter.baseline_state(), safe).verdict == "PASS"

from app.domain.logistics import medical_logistics_contract
from app.invariant.gate import DelegationGate
from app.invariant.models import (
    ConstraintClaim,
    ConstraintOperator,
    DelegationProposal,
    DriftType,
    GateStatus,
)


def test_gate_detects_missing_objective_and_constraint() -> None:
    contract = medical_logistics_contract()
    proposal = DelegationProposal(
        task_id="T-14",
        contract_id=contract.id,
        contract_version=contract.version,
        action="choose_cheapest_route",
    )

    verdict = DelegationGate().check(contract, proposal)

    assert verdict.status == GateStatus.REPAIR
    assert {(item.drift_type, item.reference_id) for item in verdict.violations} == {
        (DriftType.OMISSION, "OBJ-1"),
        (DriftType.OMISSION, "MEDICAL_SLA"),
    }


def test_gate_detects_constraint_contradiction() -> None:
    contract = medical_logistics_contract()
    proposal = DelegationProposal(
        task_id="T-15",
        contract_id=contract.id,
        contract_version=contract.version,
        action="optimize_routes",
        objective_refs=("OBJ-1",),
        constraint_claims=(
            ConstraintClaim(
                constraint_id="MEDICAL_SLA",
                subject="medical_orders",
                metric="delivery_delay",
                operator=ConstraintOperator.GREATER_THAN_OR_EQUAL,
                value_ref="baseline.medical_delay",
            ),
        ),
    )

    verdict = DelegationGate().check(contract, proposal)

    assert verdict.violations[0].drift_type == DriftType.CONTRADICTION


def test_gate_blocks_stale_contract() -> None:
    contract = medical_logistics_contract()
    proposal = DelegationProposal(
        task_id="T-16",
        contract_id=contract.id,
        contract_version=2,
        action="optimize_routes",
    )

    verdict = DelegationGate().check(contract, proposal)

    assert verdict.status == GateStatus.BLOCK
    assert verdict.violations[0].drift_type == DriftType.STALE_CONTRACT


def test_gate_detects_objective_substitution() -> None:
    contract = medical_logistics_contract()
    proposal = DelegationProposal(
        task_id="T-17",
        contract_id=contract.id,
        contract_version=contract.version,
        action="maximize_throughput",
        objective_refs=("OBJ-OTHER",),
    )

    verdict = DelegationGate().check(contract, proposal)

    assert any(
        violation.drift_type == DriftType.OBJECTIVE_SUBSTITUTION
        for violation in verdict.violations
    )



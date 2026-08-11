from app.domain.logistics import medical_logistics_contract
from app.invariant.gate import DelegationGate
from app.invariant.models import DelegationProposal, GateStatus
from app.invariant.repair import repair_delegation


def test_missing_medical_sla_is_repaired_and_rechecked() -> None:
    contract = medical_logistics_contract()
    proposal = DelegationProposal(
        task_id="T-14",
        contract_id=contract.id,
        contract_version=contract.version,
        action="choose_cheapest_route",
    )
    gate = DelegationGate()

    first_verdict = gate.check(contract, proposal)
    repair = repair_delegation(contract, proposal, first_verdict)
    second_verdict = gate.check(contract, repair.repaired)

    assert first_verdict.status == GateStatus.REPAIR
    assert repair.changed_fields == ("objective_refs", "constraint_claims")
    assert repair.repaired.objective_refs == ("OBJ-1",)
    assert repair.repaired.constraint_claims[0].constraint_id == "MEDICAL_SLA"
    assert second_verdict.status == GateStatus.PASS
    assert second_verdict.violations == ()


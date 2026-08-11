import asyncio

from app.domain.logistics import medical_logistics_contract
from app.invariant.models import (
    ConstraintClaim,
    ConstraintOperator,
    DelegationProposal,
    SemanticConstraint,
)
from app.invariant.semantic import (
    DEFAULT_MODEL,
    ESCALATION_MODEL,
    ModelCallRecord,
    SemanticVerdict,
    SemanticVerifier,
)
from tests.test_workflow import run_workflow, workflow_request


def semantic_contract():
    contract = medical_logistics_contract()
    return contract.model_copy(
        update={
            "semantic_constraints": (
                SemanticConstraint(
                    id="MEDICAL_PRIORITY",
                    rule="Economy routing must not deprioritize protected medical orders.",
                    source_span="do not delay medical orders",
                ),
            )
        }
    )


def preserved_proposal(contract) -> DelegationProposal:
    return DelegationProposal(
        task_id="T-semantic",
        contract_id=contract.id,
        contract_version=contract.version,
        action="Prioritize economy shipments wherever possible",
        objective_refs=("OBJ-1",),
        constraint_claims=(
            ConstraintClaim(
                constraint_id="MEDICAL_SLA",
                subject="medical_orders",
                metric="delivery_delay",
                operator=ConstraintOperator.LESS_THAN_OR_EQUAL,
                value_ref="baseline.medical_delay",
            ),
        ),
        semantic_invariant_refs=("MEDICAL_PRIORITY",),
    )


def test_semantic_verifier_escalates_low_confidence_to_flash() -> None:
    calls = []

    async def fake_call(model, _prompt, reason):
        calls.append((model, reason))
        if model == DEFAULT_MODEL:
            verdict = SemanticVerdict(
                preserved=True,
                confidence=0.4,
                uncertain=True,
                evidence="ambiguous",
            )
        else:
            verdict = SemanticVerdict(
                preserved=True,
                confidence=0.96,
                evidence="constraint preserved",
            )
        return verdict, ModelCallRecord(model=model, escalation_reason=reason)

    contract = semantic_contract()
    result = asyncio.run(
        SemanticVerifier(fake_call).verify(
            preserved_proposal(contract),
            contract.semantic_constraints,
            remaining_calls=5,
        )
    )

    assert result.verdict.preserved is True
    assert calls == [
        (DEFAULT_MODEL, None),
        (ESCALATION_MODEL, "low_confidence_or_semantic_ambiguity"),
    ]


def test_graph_repairs_semantic_drift_then_rechecks() -> None:
    prompts = []

    async def fake_call(model, prompt, reason):
        prompts.append(prompt)
        repaired = "Preserve invariant:" in prompt
        verdict = SemanticVerdict(
            preserved=repaired,
            violation_ids=() if repaired else ("MEDICAL_PRIORITY",),
            confidence=0.95,
            evidence="preserved" if repaired else "medical priority may be lost",
        )
        return verdict, ModelCallRecord(model=model, escalation_reason=reason)

    contract = semantic_contract()
    result, state, _ = run_workflow(
        workflow_request(
            contract=contract,
            planner_output=preserved_proposal(contract),
        ),
        semantic_verifier=SemanticVerifier(fake_call),
    )

    assert result.status == "COMPLETED"
    assert result.repair_count == 1
    assert result.llm_call_count == 2
    assert len(result.model_calls) == 2
    assert state["llm_call_count"] == 2
    assert "Preserve invariant:" not in prompts[0]
    assert "Preserve invariant:" in prompts[1]


def test_graph_blocks_uncertain_semantics_when_budget_cannot_escalate() -> None:
    async def uncertain_call(model, _prompt, reason):
        return (
            SemanticVerdict(
                preserved=True,
                confidence=0.2,
                uncertain=True,
                evidence="cannot prove protected orders remain safe",
            ),
            ModelCallRecord(model=model, escalation_reason=reason),
        )

    contract = semantic_contract()
    result, _, _ = run_workflow(
        workflow_request(
            contract=contract,
            planner_output=preserved_proposal(contract),
        ),
        semantic_verifier=SemanticVerifier(uncertain_call),
        max_llm_calls=1,
    )

    assert result.status == "BLOCKED"
    assert result.llm_call_count == 1
    assert result.violations[0].reference_id == "semantic_verifier"


def test_low_confidence_becomes_uncertain_without_escalation_budget() -> None:
    async def low_confidence_call(model, _prompt, reason):
        return (
            SemanticVerdict(
                preserved=True,
                confidence=0.2,
                uncertain=False,
                evidence="weak evidence",
            ),
            ModelCallRecord(model=model, escalation_reason=reason),
        )

    contract = semantic_contract()
    result = asyncio.run(
        SemanticVerifier(low_confidence_call).verify(
            preserved_proposal(contract),
            contract.semantic_constraints,
            remaining_calls=1,
        )
    )

    assert result.verdict.uncertain is True


def test_deterministic_drift_blocks_before_semantic_call() -> None:
    async def forbidden_call(_model, _prompt, _reason):
        raise AssertionError("semantic model called before deterministic drift resolved")

    contract = semantic_contract()
    incomplete = DelegationProposal(
        task_id="T-incomplete",
        contract_id=contract.id,
        contract_version=contract.version,
        action="choose cheapest route",
    )

    result, _, _ = run_workflow(
        workflow_request(contract=contract, planner_output=incomplete),
        semantic_verifier=SemanticVerifier(forbidden_call),
        max_repairs=0,
    )

    assert result.status == "BLOCKED"
    assert result.llm_call_count == 0

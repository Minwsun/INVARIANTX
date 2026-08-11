from app.invariant.models import (
    Constraint,
    ConstraintClaim,
    DelegationProposal,
    DriftType,
    GateVerdict,
    IntentContract,
    RepairResult,
)


def repair_delegation(
    contract: IntentContract,
    proposal: DelegationProposal,
    verdict: GateVerdict,
) -> RepairResult:
    repairable = {DriftType.OMISSION, DriftType.WEAKENING, DriftType.CONTRADICTION}
    if any(violation.drift_type not in repairable for violation in verdict.violations):
        raise ValueError("verdict contains non-repairable drift")

    objective_refs = list(proposal.objective_refs)
    claims = {claim.constraint_id: claim for claim in proposal.constraint_claims}
    changed_fields: list[str] = []

    for violation in verdict.violations:
        objective = next(
            (item for item in contract.objectives if item.id == violation.reference_id),
            None,
        )
        if objective is not None and objective.id not in objective_refs:
            objective_refs.append(objective.id)
            if "objective_refs" not in changed_fields:
                changed_fields.append("objective_refs")
            continue

        constraint = next(
            (
                item
                for item in contract.hard_constraints
                if item.id == violation.reference_id
            ),
            None,
        )
        if constraint is not None:
            claims[constraint.id] = _claim_from_constraint(constraint)
            if "constraint_claims" not in changed_fields:
                changed_fields.append("constraint_claims")

    repaired = proposal.model_copy(
        update={
            "objective_refs": tuple(objective_refs),
            "constraint_claims": tuple(claims.values()),
        }
    )
    return RepairResult(
        original=proposal,
        repaired=repaired,
        changed_fields=tuple(changed_fields),
    )


def _claim_from_constraint(constraint: Constraint) -> ConstraintClaim:
    return ConstraintClaim(
        constraint_id=constraint.id,
        subject=constraint.subject,
        metric=constraint.metric,
        operator=constraint.operator,
        value=constraint.value,
        value_ref=constraint.value_ref,
    )



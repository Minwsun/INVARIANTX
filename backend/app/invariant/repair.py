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
    semantic_refs = list(proposal.semantic_invariant_refs)
    action = proposal.action
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
            continue

        semantic_constraint = next(
            (
                item
                for item in contract.semantic_constraints
                if item.id == violation.reference_id
            ),
            None,
        )
        if semantic_constraint is not None:
            if semantic_constraint.id not in semantic_refs:
                semantic_refs.append(semantic_constraint.id)
                if "semantic_invariant_refs" not in changed_fields:
                    changed_fields.append("semantic_invariant_refs")
            safeguard = f" Preserve invariant: {semantic_constraint.rule}"
            if safeguard not in action:
                action = f"{action.rstrip('.')}.{safeguard}"
                if "action" not in changed_fields:
                    changed_fields.append("action")

    repaired = proposal.model_copy(
        update={
            "objective_refs": tuple(objective_refs),
            "constraint_claims": tuple(claims.values()),
            "semantic_invariant_refs": tuple(semantic_refs),
            "action": action,
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


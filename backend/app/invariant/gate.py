from app.invariant.models import (
    Constraint,
    ConstraintClaim,
    ConstraintOperator,
    DelegationProposal,
    DriftType,
    GateStatus,
    GateVerdict,
    IntentContract,
    Violation,
)


class DelegationGate:
    def check(
        self,
        contract: IntentContract,
        proposal: DelegationProposal,
    ) -> GateVerdict:
        if (
            proposal.contract_id != contract.id
            or proposal.contract_version != contract.version
        ):
            return GateVerdict(
                status=GateStatus.BLOCK,
                violations=(
                    Violation(
                        drift_type=DriftType.STALE_CONTRACT,
                        reference_id=proposal.contract_id,
                        evidence="proposal does not reference the active contract version",
                    ),
                ),
            )

        violations = [
            *self._check_objectives(contract, proposal),
            *self._check_constraints(contract, proposal),
            *self._check_semantic_references(contract, proposal),
        ]
        return GateVerdict(
            status=GateStatus.REPAIR if violations else GateStatus.PASS,
            violations=tuple(violations),
        )

    def _check_objectives(
        self,
        contract: IntentContract,
        proposal: DelegationProposal,
    ) -> list[Violation]:
        required = {objective.id for objective in contract.objectives}
        proposed = set(proposal.objective_refs)
        missing = required - proposed
        unknown = proposed - required
        violations = [
            Violation(
                drift_type=DriftType.OMISSION,
                reference_id=objective_id,
                evidence="required objective is missing from delegation",
            )
            for objective_id in sorted(missing)
        ]
        violations.extend(
            Violation(
                drift_type=DriftType.OBJECTIVE_SUBSTITUTION,
                reference_id=objective_id,
                evidence="delegation references an objective outside the active contract",
            )
            for objective_id in sorted(unknown)
        )
        return violations

    def _check_semantic_references(
        self,
        contract: IntentContract,
        proposal: DelegationProposal,
    ) -> list[Violation]:
        required = {constraint.id for constraint in contract.semantic_constraints}
        missing = required - set(proposal.semantic_invariant_refs)
        return [
            Violation(
                drift_type=DriftType.OMISSION,
                reference_id=constraint_id,
                evidence="semantic invariant is missing from delegation",
            )
            for constraint_id in sorted(missing)
        ]

    def _check_constraints(
        self,
        contract: IntentContract,
        proposal: DelegationProposal,
    ) -> list[Violation]:
        claims = {claim.constraint_id: claim for claim in proposal.constraint_claims}
        violations: list[Violation] = []
        for constraint in contract.hard_constraints:
            claim = claims.get(constraint.id)
            if claim is None:
                violations.append(
                    Violation(
                        drift_type=DriftType.OMISSION,
                        reference_id=constraint.id,
                        evidence="hard constraint is missing from delegation",
                    )
                )
                continue
            drift = self._compare_constraint(constraint, claim)
            if drift is not None:
                violations.append(
                    Violation(
                        drift_type=drift,
                        reference_id=constraint.id,
                        evidence="delegated constraint does not preserve the contract",
                    )
                )
        return violations

    def _compare_constraint(
        self,
        constraint: Constraint,
        claim: ConstraintClaim,
    ) -> DriftType | None:
        if constraint.subject != claim.subject or constraint.metric != claim.metric:
            return DriftType.CONTRADICTION
        if constraint.operator != claim.operator:
            return DriftType.CONTRADICTION
        if constraint.value_ref is not None:
            return None if constraint.value_ref == claim.value_ref else DriftType.WEAKENING
        if claim.value is None or constraint.value is None:
            return DriftType.WEAKENING
        if constraint.operator == ConstraintOperator.LESS_THAN_OR_EQUAL:
            return DriftType.WEAKENING if claim.value > constraint.value else None
        if constraint.operator == ConstraintOperator.GREATER_THAN_OR_EQUAL:
            return DriftType.WEAKENING if claim.value < constraint.value else None
        return None if claim.value == constraint.value else DriftType.CONTRADICTION


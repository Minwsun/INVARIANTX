from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.invariant.digest import canonical_digest
from app.invariant.models import (
    ActionApproval,
    ActionGateResult,
    ActionProposal,
    Constraint,
    ConstraintOperator,
    DriftType,
    GateStatus,
    GateVerdict,
    IntentContract,
    ToolRisk,
    Violation,
)


class ActionGate:
    def __init__(self, approval_ttl: timedelta = timedelta(seconds=60)) -> None:
        self._approval_ttl = approval_ttl

    def check(
        self,
        contract: IntentContract,
        proposal: ActionProposal,
        state: dict[str, float],
        now: datetime | None = None,
    ) -> ActionGateResult:
        current_time = now or datetime.now(timezone.utc)
        violations = self._check_references(contract, proposal)
        if not violations:
            violations.extend(self._check_permission(contract, proposal))
        if not violations and proposal.risk == ToolRisk.SIDE_EFFECT:
            violations.extend(self._check_constraints(contract, proposal, state))
        if violations:
            return ActionGateResult(
                verdict=GateVerdict(status=GateStatus.BLOCK, violations=tuple(violations))
            )

        approval = ActionApproval(
            approval_id=f"approval_{uuid4().hex}",
            contract_id=contract.id,
            contract_version=contract.version,
            tool_name=proposal.tool_name,
            arguments_digest=canonical_digest(proposal.arguments),
            state_digest=canonical_digest(state),
            expires_at=current_time + self._approval_ttl,
        )
        return ActionGateResult(
            verdict=GateVerdict(status=GateStatus.PASS),
            approval=approval,
        )

    def verify_approval(
        self,
        contract: IntentContract,
        proposal: ActionProposal,
        approval: ActionApproval | None,
        state: dict[str, float],
        now: datetime | None = None,
    ) -> GateVerdict:
        if approval is None:
            return self._blocked(
                DriftType.INSUFFICIENT_EVIDENCE,
                proposal.tool_name,
                "side-effecting action has no approval",
            )
        current_time = now or datetime.now(timezone.utc)
        if current_time >= approval.expires_at:
            return self._blocked(
                DriftType.EXPIRED_APPROVAL,
                approval.approval_id,
                "action approval has expired",
            )
        if (
            approval.contract_id != contract.id
            or approval.contract_version != contract.version
            or proposal.contract_id != contract.id
            or proposal.contract_version != contract.version
        ):
            return self._blocked(
                DriftType.STALE_CONTRACT,
                proposal.contract_id,
                "action approval does not match the active contract version",
            )
        if approval.tool_name != proposal.tool_name:
            return self._blocked(
                DriftType.ARGUMENT_MUTATION,
                proposal.tool_name,
                "approved tool name was changed",
            )
        if approval.arguments_digest != canonical_digest(proposal.arguments):
            return self._blocked(
                DriftType.ARGUMENT_MUTATION,
                proposal.action_id,
                "approved tool arguments were changed",
            )
        if approval.state_digest != canonical_digest(state):
            return self._blocked(
                DriftType.ARGUMENT_MUTATION,
                proposal.action_id,
                "state changed after action approval",
            )
        return GateVerdict(status=GateStatus.PASS)

    def _check_references(
        self,
        contract: IntentContract,
        proposal: ActionProposal,
    ) -> list[Violation]:
        if (
            proposal.contract_id == contract.id
            and proposal.contract_version == contract.version
        ):
            return []
        return [
            Violation(
                drift_type=DriftType.STALE_CONTRACT,
                reference_id=proposal.contract_id,
                evidence="action does not reference the active contract version",
            )
        ]

    def _check_permission(
        self,
        contract: IntentContract,
        proposal: ActionProposal,
    ) -> list[Violation]:
        allowed = any(
            permission.tool_name == proposal.tool_name
            and permission.risk == proposal.risk
            for permission in contract.permissions
        )
        if allowed:
            return []
        return [
            Violation(
                drift_type=DriftType.UNAUTHORIZED_ACTION,
                reference_id=proposal.tool_name,
                evidence="tool or risk level is not allowed by the contract",
            )
        ]

    def _check_constraints(
        self,
        contract: IntentContract,
        proposal: ActionProposal,
        state: dict[str, float],
    ) -> list[Violation]:
        violations: list[Violation] = []
        for constraint in contract.hard_constraints:
            proposed_value = proposal.proposed_metrics.get(constraint.metric)
            expected_value = self._expected_value(constraint, state)
            if proposed_value is None or expected_value is None:
                violations.append(
                    Violation(
                        drift_type=DriftType.INSUFFICIENT_EVIDENCE,
                        reference_id=constraint.id,
                        evidence="side effect lacks metrics required to prove constraint safety",
                    )
                )
            elif not self._satisfies(constraint.operator, proposed_value, expected_value):
                violations.append(
                    Violation(
                        drift_type=DriftType.CONTRADICTION,
                        reference_id=constraint.id,
                        evidence="proposed side effect violates a hard constraint",
                    )
                )
        return violations

    def _expected_value(
        self,
        constraint: Constraint,
        state: dict[str, float],
    ) -> float | None:
        if constraint.value is not None:
            return constraint.value
        return state.get(constraint.value_ref or "")

    def _satisfies(
        self,
        operator: ConstraintOperator,
        proposed: float,
        expected: float,
    ) -> bool:
        if operator == ConstraintOperator.LESS_THAN_OR_EQUAL:
            return proposed <= expected
        if operator == ConstraintOperator.GREATER_THAN_OR_EQUAL:
            return proposed >= expected
        return proposed == expected

    def _blocked(
        self,
        drift_type: DriftType,
        reference_id: str,
        evidence: str,
    ) -> GateVerdict:
        return GateVerdict(
            status=GateStatus.BLOCK,
            violations=(
                Violation(
                    drift_type=drift_type,
                    reference_id=reference_id,
                    evidence=evidence,
                ),
            ),
        )

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PositiveInt, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConstraintOperator(StrEnum):
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    EQUAL = "equal"


class ObjectiveOperator(StrEnum):
    DECREASE_BY = "decrease_by"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    EQUAL = "equal"


class Unit(StrEnum):
    RATIO = "ratio"
    PERCENT = "percent"


class DriftType(StrEnum):
    OMISSION = "OMISSION"
    CONTRADICTION = "CONTRADICTION"
    WEAKENING = "WEAKENING"
    OBJECTIVE_SUBSTITUTION = "OBJECTIVE_SUBSTITUTION"
    STALE_CONTRACT = "STALE_CONTRACT"
    UNAUTHORIZED_ACTION = "UNAUTHORIZED_ACTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ARGUMENT_MUTATION = "ARGUMENT_MUTATION"
    EXPIRED_APPROVAL = "EXPIRED_APPROVAL"


class GateStatus(StrEnum):
    PASS = "PASS"
    REPAIR = "REPAIR"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class ToolRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    SIDE_EFFECT = "SIDE_EFFECT"


class EvidenceType(StrEnum):
    SIMULATOR = "simulator"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class Objective(FrozenModel):
    id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: ObjectiveOperator
    target: float
    unit: Unit
    reference: str = Field(min_length=1)
    source_span: str = Field(min_length=1)


class Constraint(FrozenModel):
    id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: ConstraintOperator
    value: float | None = None
    value_ref: str | None = None
    source_span: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_one_value(self) -> Constraint:
        if (self.value is None) == (self.value_ref is None):
            raise ValueError("exactly one of value or value_ref is required")
        return self


class Permission(FrozenModel):
    tool_name: str = Field(min_length=1)
    risk: ToolRisk


class SemanticConstraint(FrozenModel):
    id: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    source_span: str = Field(min_length=1)


class IntentContract(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(min_length=1)
    version: PositiveInt
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    original_request: str = Field(min_length=1)
    objectives: tuple[Objective, ...] = Field(min_length=1)
    hard_constraints: tuple[Constraint, ...] = ()
    protected_entities: tuple[str, ...] = ()
    forbidden_outcomes: tuple[str, ...] = ()
    permissions: tuple[Permission, ...] = ()
    semantic_constraints: tuple[SemanticConstraint, ...] = ()

    @model_validator(mode="after")
    def require_unique_ids(self) -> IntentContract:
        ids = [
            item.id
            for item in (
                *self.objectives,
                *self.hard_constraints,
                *self.semantic_constraints,
            )
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("objective and constraint ids must be unique")
        return self


class IntentContractCandidate(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    objectives: tuple[Objective, ...] = Field(min_length=1)
    hard_constraints: tuple[Constraint, ...] = ()
    protected_entities: tuple[str, ...] = ()
    forbidden_outcomes: tuple[str, ...] = ()
    semantic_constraints: tuple[SemanticConstraint, ...] = ()

    @model_validator(mode="after")
    def require_unique_ids(self) -> IntentContractCandidate:
        ids = [
            item.id
            for item in (
                *self.objectives,
                *self.hard_constraints,
                *self.semantic_constraints,
            )
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("objective and constraint ids must be unique")
        return self


class RawObjective(FrozenModel):
    id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    target: float
    unit: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    source_span: str = Field(min_length=1)


class RawConstraint(FrozenModel):
    id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    value: float | None = None
    value_ref: str | None = None
    source_span: str = Field(min_length=1)


class RawIntentContractCandidate(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    objectives: tuple[RawObjective, ...] = Field(min_length=1)
    hard_constraints: tuple[RawConstraint, ...] = ()
    protected_entities: tuple[str, ...] = ()
    forbidden_outcomes: tuple[str, ...] = ()
    semantic_constraints: tuple[SemanticConstraint, ...] = ()


class ConstraintClaim(FrozenModel):
    constraint_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: ConstraintOperator
    value: float | None = None
    value_ref: str | None = None

    @model_validator(mode="after")
    def require_one_value(self) -> ConstraintClaim:
        if (self.value is None) == (self.value_ref is None):
            raise ValueError("exactly one of value or value_ref is required")
        return self


class DelegationProposal(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    task_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_version: PositiveInt
    action: str = Field(min_length=1)
    objective_refs: tuple[str, ...] = ()
    constraint_claims: tuple[ConstraintClaim, ...] = ()
    semantic_invariant_refs: tuple[str, ...] = ()


class Violation(FrozenModel):
    drift_type: DriftType
    reference_id: str
    evidence: str


class GateVerdict(FrozenModel):
    status: GateStatus
    violations: tuple[Violation, ...] = ()


class ActionProposal(FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    action_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_version: PositiveInt
    tool_name: str = Field(min_length=1)
    risk: ToolRisk
    arguments: dict[str, JsonValue]
    proposed_metrics: dict[str, float] = Field(default_factory=dict)


class ActionApproval(FrozenModel):
    approval_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_version: PositiveInt
    tool_name: str = Field(min_length=1)
    arguments_digest: str = Field(min_length=64, max_length=64)
    state_digest: str = Field(min_length=64, max_length=64)
    expires_at: datetime


class ActionGateResult(FrozenModel):
    verdict: GateVerdict
    approval: ActionApproval | None = None


class EvidenceSource(FrozenModel):
    type: EvidenceType
    adapter: str = Field(min_length=1)
    reference: str | None = None


class ExecutionReceipt(FrozenModel):
    status: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    actual_metrics: dict[str, float] = Field(default_factory=dict)
    before_metrics: dict[str, float] = Field(default_factory=dict)
    dataset_version: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    capacity_violations: tuple[str, ...] = ()
    sla_violations: tuple[str, ...] = ()
    assignment_summary: dict[str, int] = Field(default_factory=dict)
    occurred_outcomes: tuple[str, ...] = ()
    protected_entities: dict[str, bool] = Field(default_factory=dict)
    evidence_source: EvidenceSource

    @classmethod
    def unknown(cls, *, plan_id: str, adapter: str, reference: str) -> ExecutionReceipt:
        return cls(
            status="unknown",
            plan_id=plan_id,
            evidence_source=EvidenceSource(
                type=EvidenceType.UNKNOWN,
                adapter=adapter,
                reference=reference,
            ),
        )


class ValidationResult(FrozenModel):
    verdict: Literal["PASS", "BLOCK"]
    objective_status: dict[str, bool] = Field(default_factory=dict)
    constraint_status: dict[str, bool] = Field(default_factory=dict)
    violations: tuple[Violation, ...] = ()


class RepairResult(FrozenModel):
    original: DelegationProposal
    repaired: DelegationProposal
    changed_fields: tuple[str, ...]

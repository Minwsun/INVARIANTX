from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ConstraintOperator(StrEnum):
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    EQUAL = "equal"


class DriftType(StrEnum):
    OMISSION = "OMISSION"
    CONTRADICTION = "CONTRADICTION"
    WEAKENING = "WEAKENING"
    OBJECTIVE_SUBSTITUTION = "OBJECTIVE_SUBSTITUTION"
    STALE_CONTRACT = "STALE_CONTRACT"


class GateStatus(StrEnum):
    PASS = "PASS"
    REPAIR = "REPAIR"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class Objective(FrozenModel):
    id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    target: float
    unit: str = Field(min_length=1)
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

    @model_validator(mode="after")
    def require_unique_ids(self) -> IntentContract:
        ids = [item.id for item in (*self.objectives, *self.hard_constraints)]
        if len(ids) != len(set(ids)):
            raise ValueError("objective and constraint ids must be unique")
        return self


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


class Violation(FrozenModel):
    drift_type: DriftType
    reference_id: str
    evidence: str


class GateVerdict(FrozenModel):
    status: GateStatus
    violations: tuple[Violation, ...] = ()


class RepairResult(FrozenModel):
    original: DelegationProposal
    repaired: DelegationProposal
    changed_fields: tuple[str, ...]


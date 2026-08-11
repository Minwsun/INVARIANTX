# Intent Contract Specification v1

This document defines the immutable source of truth for a run.

## Principles

- The contract captures **what** the human wants, not the implementation plan.
- Hard constraints cannot be weakened by priorities, plans, repairs, or optimization.
- Agents may read contract projections but cannot create replacement truth.
- User-authorized intent changes create a new version; previous versions remain auditable.
- Every field is typed, bounded, and attributable to source text.

## Pydantic Model Shape

```python
class IntentContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"]
    id: str
    version: PositiveInt
    created_at: datetime
    source: IntentSource
    objectives: tuple[Objective, ...]
    hard_constraints: tuple[Constraint, ...]
    priorities: tuple[Priority, ...] = ()
    protected_entities: tuple[ProtectedEntity, ...] = ()
    forbidden_outcomes: tuple[ForbiddenOutcome, ...] = ()
    permissions: tuple[Permission, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
```

Production code must use equivalent immutable Pydantic models. Tuple fields prevent accidental collection mutation.

## Required Types

### `IntentSource`

Contains the original request, request hash, user/session identity reference, timestamp, and authorization source. The original request is retained for audit but is not forwarded wholesale to every agent.

### `Objective`

```json
{
  "id": "OBJ-1",
  "metric": "logistics_cost",
  "operator": "decrease_by_at_least",
  "target": 0.15,
  "unit": "ratio",
  "reference": "baseline",
  "source_span": "Reduce logistics cost by 15%"
}
```

An objective is desired and measurable. Failure to achieve it is not permission to violate a hard constraint.

### `Constraint`

```json
{
  "id": "MEDICAL_SLA",
  "kind": "hard",
  "subject": "medical_orders",
  "metric": "delivery_delay",
  "operator": "less_than_or_equal",
  "value_ref": "baseline.medical_delay",
  "scope": "all",
  "source_span": "must not delay medical orders"
}
```

Each deterministic constraint identifies subject, metric, operator, expected value or reference, and scope. Semantic constraints additionally provide a concise natural-language rule and classification tags.

### `Priority`

Defines ordering among otherwise valid choices. A priority never overrides a hard constraint or forbidden outcome.

### `ProtectedEntity`

Identifies an entity class requiring explicit preservation checks, such as medical orders, users, funds, or production records.

### `ForbiddenOutcome`

Defines a state that must not occur, independent of the chosen method.

### `Permission`

Defines allowed action categories and limits. Absence of permission does not imply permission for high-impact side effects.

### `Assumption`

Records compiler assumptions, confidence, and source. High-impact unresolved assumptions require escalation before side effects.

## Validation Rules

1. IDs are unique within a contract.
2. At least one objective is required.
3. Every objective and constraint contains source provenance.
4. Deterministic operators use an enumerated operator set.
5. References resolve against registered baseline or runtime facts.
6. Contradictory hard constraints prevent contract activation.
7. Ambiguous high-impact constraints prevent automatic activation.
8. Unknown fields are rejected.
9. Contract hash covers canonical serialized content excluding storage metadata.

## Immutability and Versioning

- Firestore documents are append-only by `(id, version)`.
- Existing versions cannot be overwritten.
- A new version requires a user-authorized intent update event.
- A run is pinned to one contract version unless an explicit user update transitions it.
- New versions invalidate outstanding delegation and action approvals.
- Agents cannot propose contract patches through normal agent output schemas.

## Contract Projection

Runtime sends each agent only:

- Relevant objective references.
- Applicable hard constraints.
- Applicable forbidden outcomes.
- Required permissions.
- Minimal referenced state.

Projection omission cannot remove enforcement: gates always load the complete contract from the registry.

## Logistics Demo Contract

```json
{
  "schema_version": "1.0",
  "id": "I-001",
  "version": 1,
  "objectives": [{
    "id": "OBJ-1",
    "metric": "logistics_cost",
    "operator": "decrease_by_at_least",
    "target": 0.15,
    "unit": "ratio",
    "reference": "baseline",
    "source_span": "Reduce logistics cost by 15%"
  }],
  "hard_constraints": [{
    "id": "MEDICAL_SLA",
    "kind": "hard",
    "subject": "medical_orders",
    "metric": "delivery_delay",
    "operator": "less_than_or_equal",
    "value_ref": "baseline.medical_delay",
    "scope": "all",
    "source_span": "must not delay medical orders"
  }],
  "protected_entities": [{"id": "PE-1", "type": "medical_orders"}],
  "forbidden_outcomes": [{
    "id": "FO-1",
    "description": "Deprioritize medical orders",
    "source_span": "must not delay medical orders"
  }]
}
```

Storage metadata and unchanged optional arrays are omitted from this shortened example.


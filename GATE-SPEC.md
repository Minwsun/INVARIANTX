# INVARIANT Gate Specification v1

The gates enforce the active Intent Contract. They are deterministic runtime components, not agents.

## Gate Types

### Delegation Gate

Checks a proposed task before another agent receives it.

### Action Gate

Checks a proposed side-effecting tool call immediately before execution.

Read-only tools may use a reduced policy, but still require schema validation, permission checks, and audit events.

## Input

```json
{
  "run_id": "run_123",
  "contract_id": "I-001",
  "contract_version": 1,
  "proposal": {},
  "runtime_fact_refs": ["STATE-18"],
  "risk": "high"
}
```

The gate loads the complete contract independently. It never trusts a proposal-provided contract projection as source of truth.

## Drift Taxonomy

| Type | Meaning |
| --- | --- |
| `OMISSION` | Required objective, constraint, permission, or protected entity is absent |
| `CONTRADICTION` | Proposal directly conflicts with the contract |
| `WEAKENING` | Proposal reduces scope or strength of a requirement |
| `OBJECTIVE_SUBSTITUTION` | Proposal optimizes a different objective |
| `SCOPE_EXPANSION` | Proposal affects entities or actions outside authorized scope |
| `FORBIDDEN_OUTCOME_RISK` | Proposal may produce a prohibited state |
| `STALE_CONTRACT` | Proposal or approval references an inactive version |
| `ARGUMENT_MUTATION` | Tool arguments differ from approved normalized arguments |
| `INSUFFICIENT_EVIDENCE` | Safety cannot be established from available facts |

## Evaluation Order

1. Validate input schema and references.
2. Load active contract and runtime facts.
3. Determine proposal materiality and risk.
4. Run deterministic structural checks.
5. Run deterministic domain evaluators.
6. If unresolved semantics remain, call Flash-Lite.
7. If high-impact uncertainty remains, call Flash only when budget allows.
8. Aggregate violations without allowing semantic output to override deterministic failures.
9. Emit a verdict and evidence.

## Verdicts

### `PASS`

No unresolved violation exists. Action Gate produces a short-lived approval binding:

- Contract ID and version.
- Tool name.
- Canonical argument digest.
- Relevant state version or digest.
- Expiration time.
- Gate verdict ID.

### `REPAIR`

The proposal is unsafe but can be minimally corrected without changing human intent. The verdict specifies violations and repairable fields.

### `BLOCK`

The action is forbidden, deterministic safety failed, approval is stale, budget is exhausted, or required runtime integrity is unavailable.

### `ESCALATE`

Human clarification is required because intent is conflicting, high-impact ambiguity remains, or automatic repair would choose new intent.

## Deterministic Rules

- Required invariant references must be retained in delegations.
- Hard constraints must be represented in task success criteria when relevant.
- Numeric bounds are evaluated in Python.
- Protected entities remain in scope for applicable actions.
- Tool and arguments must satisfy permissions.
- Forbidden outcomes are checked against simulations or known effects.
- Contract version and approval digest must match at execution time.

## Semantic Fallback

Semantic verification receives only the proposal, relevant contract clauses, concise facts, and a fixed output schema. It returns preservation status, violation IDs, evidence, and confidence.

- Flash-Lite is first.
- Flash is escalation only.
- Low confidence on a high-risk action cannot produce `PASS`.
- Semantic `PASS` cannot override a deterministic violation.

## Repair Protocol

1. Gate emits `REPAIR` with typed violations.
2. Repair Agent changes only listed repairable fields.
3. Runtime validates the repaired proposal.
4. The same gate performs a fresh full check.
5. Passed repair resumes execution.
6. Failed repair repeats only within run and call budgets.
7. Exhaustion produces `BLOCK` or `ESCALATE`.

Default limits: two repair attempts per proposal and five total LLM calls per run.

## Side-Effect Enforcement

The ADK `before_tool_callback` is the final enforcement point. It validates the approval binding against the exact invocation. A missing or invalid approval returns a typed `INTENT_VIOLATION` result and prevents tool execution.

No prompt instruction, agent role, or graph route can bypass this callback.

## Logistics Demo Checks

- `medical_delay <= baseline.medical_delay` is deterministic.
- `cost_reduction >= 0.15` is deterministic.
- `apply_plan` is side-effecting and always gated.
- A plan that chooses the cheapest route without preserving `MEDICAL_SLA` receives `REPAIR`.
- A simulated plan that increases medical delay receives `BLOCK`, even if semantic verification approves it.


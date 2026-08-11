# Agent Protocol v1

Agents communicate through schema-validated JSON. They do not chat with each other.

## Common Envelope

Every agent output uses:

```json
{
  "schema_version": "1.0",
  "run_id": "run_123",
  "message_id": "msg_123",
  "agent": "planner",
  "contract_id": "I-001",
  "contract_version": 1,
  "payload": {}
}
```

Unknown fields, invalid references, stale contract versions, and prose outside the JSON object are rejected.

## Intent Compiler

Input:

- Original user request.
- Supported contract schema.
- Available domain vocabulary, when present.

Output: `IntentContractCandidate` containing objectives, hard constraints, priorities, protected entities, forbidden outcomes, permissions, assumptions, source spans, and confidence values.

The compiler does not activate or persist a contract. Runtime validation and registration do.

## Planner

Input:

- Contract projection.
- Available capabilities and tool summaries.
- Compact run state.

Output:

```json
{
  "task_id": "T-14",
  "action": "optimize_routes",
  "objective_refs": ["OBJ-1"],
  "required_invariants": ["MEDICAL_SLA"],
  "required_tools": ["simulate_plan"],
  "state_ref": "STATE-18",
  "success_criteria": ["cost_reduction >= 0.15"]
}
```

Planner cannot invoke tools or delegate directly. Runtime gates the proposal.

## Worker

Input:

- Passed `DelegationProposal`.
- Relevant contract projection.
- Allowed tool schemas.
- Referenced domain state.

Output is one of:

- `ActionProposal` for a tool call.
- `WorkResult` for computation requiring no side effect.
- `CannotProceed` with typed missing facts or conflicts.

`ActionProposal` contains tool name, JSON arguments, expected effect, objective references, invariant references, and required permissions.

## Repair Agent

Input:

```json
{
  "proposal": {},
  "violations": [{
    "constraint_id": "MEDICAL_SLA",
    "kind": "omission",
    "evidence": "No medical delay restriction appears in the task"
  }],
  "repairable_fields": ["required_invariants", "success_criteria"]
}
```

Output: `RepairResult` containing a minimally changed replacement proposal, changed fields, preserved fields, and a concise repair reason.

The Repair Agent cannot alter objective meaning, contract data, tool results, or runtime facts.

## Validator

Input:

- Contract projection.
- Execution result references.
- Before/after deterministic metrics.
- Tool receipt and gate verdict reference.

Output: `ValidationResult` with objective status, constraint status, evidence references, confidence, and final verdict.

Validator prose is not authoritative. Deterministic result checks override conflicting semantic output.

## Output Limits

- JSON only.
- No chain-of-thought or hidden reasoning request.
- Output target under 150 tokens per model call.
- Human-readable fields are concise evidence summaries, not essays.
- Payloads reference large state and artifacts by ID.

## Runtime Validation

1. Parse strict JSON.
2. Validate Pydantic schema.
3. Confirm run and contract references.
4. Reject unauthorized fields and stale versions.
5. Normalize proposal.
6. Emit typed event.
7. Route to the applicable gate or next deterministic node.

One schema-repair attempt is permitted only when the total LLM-call budget remains available.


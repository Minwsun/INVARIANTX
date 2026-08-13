# INVARIANT Event Specification v1

Events are the communication and audit primitive between runtime nodes and the frontend.

## Envelope

```json
{
  "schema_version": "1.0",
  "event_id": "evt_01J...",
  "sequence": 14,
  "type": "DRIFT_DETECTED",
  "timestamp": "2026-08-11T09:42:03.123Z",
  "run_id": "run_123",
  "contract_id": "I-001",
  "contract_version": 1,
  "causation_id": "evt_01H...",
  "correlation_id": "task_T-14",
  "actor": "delegation_gate",
  "payload": {}
}
```

`sequence` is monotonically increasing within one run. Timestamps are UTC. Unknown event fields are rejected by consumers that require strict validation.

## Event Types

### Lifecycle

- `RUN_CREATED`
- `RUN_STARTED`
- `RUN_CANCEL_REQUESTED`
- `RUN_CANCELLED`
- `RUN_COMPLETED`
- `RUN_FAILED`
- `RUN_ESCALATED`

### Contract

- `CONTRACT_COMPILED`
- `CONTRACT_REGISTERED`
- `CONTRACT_REJECTED`
- `CONTRACT_VERSION_CREATED`

### Agent and Task

- `AGENT_STARTED`
- `AGENT_COMPLETED`
- `AGENT_OUTPUT_REJECTED`
- `TASK_PROPOSED`
- `ACTION_PROPOSED`

### Gate and Repair

- `GATE_STARTED`
- `GATE_PASSED`
- `DRIFT_DETECTED`
- `ACTION_BLOCKED`
- `ESCALATION_REQUIRED`
- `REPAIR_STARTED`
- `REPAIR_PROPOSED`
- `REPAIR_ACCEPTED`
- `REPAIR_REJECTED`

### Tool and Validation

- `TOOL_STARTED`
- `TOOL_COMPLETED`
- `TOOL_FAILED`
- `VALIDATION_STARTED`
- `VALIDATION_COMPLETED`

### Model and Runtime

- `MODEL_CALL_COMPLETED`
- `MODEL_CALL_LIMIT_REACHED`
- `STATE_UPDATED`
- `GATE_FAILED`

## Payload Rules

- Payloads are event-specific typed objects.
- Events reference large artifacts by ID.
- Secrets, credentials, full prompts, chain-of-thought, and sensitive raw datasets are prohibited.
- Violations include stable constraint IDs and evidence references.
- Model events include provider, model, role, attempt, outcome, token counts, latency, cache status, error type, and escalation reason.
- `MODEL_RETRY` records an observable same-model retry.
- `MODEL_FAILED` records terminal fail-closed model execution.
- `POLICY_ESCALATED` records unresolved ambiguity and maps to terminal `BLOCKED` in v3.
- `TOOL_TIMED_OUT` records ambiguous side-effect execution with `UNKNOWN` evidence.
- `RECEIPT_REJECTED` records malformed or contract-invalid execution evidence.
- Terminal events include final status, metrics summary, and result reference.

## Persistence and Ordering

- Persist the decision event before executing a side effect.
- Assign event sequence atomically per run.
- Event IDs are globally unique.
- Duplicate event delivery is allowed; duplicate event creation is not.
- Consumers deduplicate by `event_id`.
- Causal relationships use `causation_id`; task grouping uses `correlation_id`.

## SSE Mapping

Endpoint: `GET /runs/{run_id}/events`

```text
id: evt_01J...
event: DRIFT_DETECTED
data: {"schema_version":"1.0","sequence":14,...}

```

- Client reconnects with `Last-Event-ID`.
- Server replays later events from Firestore, then continues streaming live events.
- Heartbeat comments may be sent without creating journal events.
- Authorization is checked before replay and continuously for long-lived connections.
- A terminal event closes the stream after delivery.

## Frontend Projection

The frontend derives graph status, contract checks, timeline, and metrics from events plus run snapshots. It does not infer authorization or recompute verdicts.

## Minimal Run Sequence

```text
RUN_CREATED
RUN_STARTED
CONTRACT_COMPILED
CONTRACT_REGISTERED
TASK_PROPOSED
GATE_STARTED
GATE_PASSED | DRIFT_DETECTED
REPAIR_STARTED?
REPAIR_ACCEPTED?
ACTION_PROPOSED
GATE_STARTED
GATE_PASSED | ACTION_BLOCKED
TOOL_STARTED?
TOOL_COMPLETED?
VALIDATION_STARTED
VALIDATION_COMPLETED
RUN_COMPLETED | RUN_FAILED | RUN_ESCALATED
```

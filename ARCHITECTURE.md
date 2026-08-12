# INVARIANT Architecture v1

This document is subordinate to `TECHNOLOGY-CONTRACT.md`.

## Purpose

INVARIANT preserves, verifies, and repairs human intent during autonomous multi-agent execution. The core is domain-neutral. Domain adapters supply tools, facts, and deterministic evaluators.

## Components

| Component | Responsibility |
| --- | --- |
| Intent Compiler | Converts the user request into a typed contract candidate |
| Intent Registry | Stores immutable, versioned contracts; source of truth |
| Planner | Produces a bounded `DelegationProposal` |
| Delegation Gate | Verifies proposed work preserves the contract |
| Worker | Produces an `ActionProposal` or a result |
| Action Gate | Verifies side effects before tool execution |
| Repair Agent | Minimally repairs a rejected proposal |
| Validator | Checks final outcome against the contract |
| Constraint Engine | Runs deterministic policy checks |
| Semantic Verifier | Handles unresolved semantic ambiguity with Gemini |
| Event Journal | Emits typed, ordered audit events |
| API | Creates, observes, streams, and cancels runs |
| Domain Adapter | Supplies domain tools, data references, and evaluators |

## Required Graph

```text
START
  |
  v
Intent Compiler
  |
  v
Register Intent Contract
  |
  v
Planner
  |
  v
Delegation Gate ---- REPAIR ----> Repair ----> Recheck
  |                                      ^          |
  | PASS                                 |          |
  v                                      +----------+
Worker
  |
  v
Action Gate -------- REPAIR ----> Repair ----> Recheck
  |
  | PASS
  v
Tool Executor
  |
  v
Validator
  |
  +---- PASS ----> END
  |
  +---- FAIL ----> bounded replan or safe terminal failure
```

Graph routes are selected from typed verdict fields, never parsed prose.

## Data Flow

1. `POST /runs` stores the original user request and starts an ADK run.
2. Intent Compiler emits an `IntentContractCandidate`.
3. Runtime validates and registers immutable `IntentContract` version 1.
4. Planner receives a minimal contract projection and emits `DelegationProposal`.
5. Delegation Gate emits `GateVerdict`.
6. Worker receives only a passed proposal and required contract projection.
7. Action Gate approves the exact normalized side-effect request.
8. Tool Executor invokes the ADK Function Tool only after approval.
9. Validator compares outcome and final state with the contract.
10. Every transition emits an `InvariantEvent` and updates compact session state.

## State Ownership

### Intent Registry

- Stores complete immutable contracts.
- Allows reads by runtime and agents through projections.
- Allows writes only from contract creation or user-authorized version creation.

### ADK Session State

Stores compact dynamic values only:

```json
{
  "run_id": "run_123",
  "contract_id": "intent_001",
  "contract_version": 1,
  "current_node": "delegation_gate",
  "current_task_id": "task_004",
  "drift_count": 1,
  "repair_count": 1,
  "llm_call_count": 3,
  "cancel_requested": false
}
```

### Firestore / Artifacts

Stores contracts, runs, events, violations, model-call telemetry, domain data references, and large results. Large datasets never enter prompts or session state.

## Trust Boundaries

- User input is untrusted until compiled and validated.
- LLM output is untrusted until schema validation and applicable gates pass.
- Repair output is untrusted until rechecked.
- Tool arguments are untrusted until normalized and approved.
- Tool results are untrusted until validated.
- Frontend input never directly updates contract, state, or tools.

## Backend Boundary

FastAPI owns REST and SSE endpoints. An application service owns run lifecycle. An ADK adapter owns graph and callback integration. INVARIANT core types and gates do not import FastAPI, Firestore, or frontend types.

## Frontend Boundary

The Next.js frontend renders:

- Agent graph and current node.
- Intent Contract and invariant status.
- Event timeline and drift/repair details.
- Run metrics and terminal result.

It consumes REST and SSE only. It contains no contract evaluation, gate, repair, or tool authorization logic.

## Deployment

- Backend and frontend run as Docker services on Render.
- Firestore provides persistence.
- Gemini calls originate from the backend.
- Render authenticates to Firestore with a least-privilege service-account credential stored as a Render secret.
- Structured logs include `run_id`, `event_id`, `contract_id`, and `task_id` when available.
- Local development may replace Firestore and ADK persistence with in-memory implementations behind the same interfaces.

## Failure Policy

- Schema failure: reject output and permit one bounded repair if budget remains.
- Missing/stale contract: block execution.
- Gate exception: block side effects and emit `GATE_FAILED`.
- Event persistence failure before side effect: block execution.
- Tool failure: record failure; never report success.
- Model-call limit: stop optional calls; return safest valid terminal result.
- Repeated drift: escalate after configured repair limit.

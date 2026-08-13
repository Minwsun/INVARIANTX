# ADR-001: Hybrid Gemini and Gemma Runtime

Status: Accepted  
Date: 2026-08-13

## Context

Technology Contract v2 used one Gemini model for every LLM role. That coupled protocol schemas and telemetry to one model, hard-wired logistics into runtime composition, and did not represent the intended final workforce architecture.

## Decision

- Gemini 3.5 Flash-Lite compiles the human goal into the canonical Intent Contract.
- Gemma 4 31B produces Planner and Worker proposals through Google ADK.
- Python remains the authority for delegation checks, action approval, repair, tool enforcement, and final validation.
- Models are configured per role through validated environment variables.
- A failed model attempt retries the same role/model once; no cross-model fallback exists.
- Every network attempt counts toward the five-attempt run budget.
- `RunService` receives a `DomainAdapter`; `LogisticsAdapter` is the default demo implementation.
- Tools return raw results. Adapters construct evidence-labeled `ExecutionReceipt` objects.

## Consequences

- Normal runs remain three model attempts: one Gemini and two Gemma.
- Safety outcomes do not depend on a model judging its own work.
- Future fleet benchmarks can change approved environment configuration without changing public APIs.
- Tool timeout or ambiguous execution is terminal `BLOCKED`; side effects are never retried automatically.

## Rollback

Set the approved Planner and Worker environment variables to a Gemini model, revert adapter composition to the prior logistics wiring, and restore Technology Contract v2. Intent Contract and gate schemas remain compatible.

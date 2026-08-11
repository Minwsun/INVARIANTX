# Demo Script

Target length: 3 minutes.

## 1. Problem

State the North Star: agents may change execution strategy, never the human's intended outcome.

Enter:

```text
Reduce logistics cost by 15%, but do not delay medical orders.
```

## 2. Contract

Show the compiled immutable contract:

- Objective: reduce logistics cost by 15%.
- Hard invariant: `medical_delay <= baseline`.
- Protected entity: medical orders.
- Forbidden outcome: deprioritizing medical orders.

## 3. Drift

Show Planner delegation followed by Worker proposal: choose the cheapest route.

Point to timeline events:

```text
TASK_CREATED
INTENT_CHECKED
DRIFT_DETECTED
```

Explain that the worker omitted `MEDICAL_SLA`; no tool executes yet.

## 4. Repair

Show automatic repaired instruction:

```text
Choose the cheapest route while keeping medical_delay <= baseline.
```

Point to `REPAIR_APPLIED`, recheck success, and resumed execution.

## 5. Proof

Show:

- Completed graph path.
- Intent integrity score.
- Typed event audit trail.
- LLM call and token counters.
- Evaluation baseline with zero escaped violations and full drift recall.

Close: logistics is replaceable; Intent Contract, Gate, Repair, and Evaluation are the product.

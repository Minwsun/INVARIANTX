# Benchmark Layer B — Paired Live Models

Layer B runs the same natural-language goal, model routing, and logistics dataset through two fleets:

- Ungated: Gemini compiler → Gemma planner → Gemma worker → simulator → validator.
- INVARIANT: same agents and dataset, plus deterministic gates, repair, approval, and validator.

No drift injection or output mutation is used. Every failed or blocked run remains in the artifact.

```powershell
cd backend
$env:INVARIANT_API_BASE="https://invariantx-api.onrender.com"
$env:INVARIANT_DEMO_KEY="<existing Render secret>"
$env:INVARIANT_LIVE_OUTPUT="..\benchmarks\live-v1.json"
.\.venv\Scripts\python.exe -m app.evaluation.live_benchmark
Remove-Item Env:INVARIANT_DEMO_KEY
```

The initial pilot contains five paired scenarios. Increase sample size only after the pilot completes without schema, quota, or persistence failures.

## Layer B v3 result

The controlled 30-pair production run is published in `live-v3-layer-b-30.json`; the concise claim and limitations are in `live-v3-layer-b-30-summary.json`.

# Benchmark Layer A — Deterministic Safety v1

Benchmark Layer A compares an ungated execution baseline with INVARIANT v3 over the same typed corruption corpus.

## Method

- `deterministic_fixture_replay`; no live model calls.
- Nine categories, ten cases each by default.
- Baseline represents execution without Delegation Gate, Action Gate, repair, or approval binding.
- INVARIANT runs the production deterministic gates and repair policy.
- Results measure safety-layer behavior, not Gemini/Gemma semantic quality, latency, token usage, or monetary cost.

Categories: valid delegation, omission, weakening, contradiction, objective substitution, stale contract, unauthorized tool, argument mutation, and unsafe candidate plan.

Unsafe-plan cases use the production logistics projection boundary: Worker claims are replaced by simulator measurements, Action Gate blocks the unsafe plan, deterministic Action Repair selects a safe candidate, then Action Gate rechecks it.

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.evaluation `
  --benchmark `
  --cases-per-category 10 `
  --output ..\benchmarks\benchmark-v1.json
```

The generated JSON is reproducible except for `generated_at`. Benchmark Layer B will measure live Gemini-only versus Gemini + Gemma quality, latency, tokens, calls, and estimated cost. Those values must not be inferred from Layer A.

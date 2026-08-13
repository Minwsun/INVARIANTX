# Feature Freeze v3 Proof Checklist

Feature freeze requires production evidence from the deployed Render revision.

- [ ] Commit SHA recorded.
- [ ] `/ready` reports runtime and Firestore ready.
- [ ] Intent Compiler telemetry uses `gemini-3.5-flash-lite`.
- [ ] Planner telemetry uses `gemma-4-31b-it`.
- [ ] Worker telemetry uses `gemma-4-31b-it`.
- [ ] Standard run completes with exactly three successful model attempts.
- [ ] Deliberate omission emits drift detection, deterministic repair, recheck, and final PASS.
- [ ] Receipt evidence source is `simulator` / `logistics-v1`.
- [ ] Firestore persists run, immutable contract, ordered events, telemetry, receipt, and validation.
- [ ] Dashboard screenshot shows hybrid routing and terminal integrity.
- [ ] Tool timeout fixture produces `UNKNOWN` evidence and terminal `BLOCKED`.
- [ ] Backend tests, frontend tests, frontend build, and CI pass.

Do not begin benchmark work until every item is checked with real production artifacts.

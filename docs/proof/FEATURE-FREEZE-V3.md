# Feature Freeze v3 Proof Checklist

Feature freeze requires production evidence from the deployed Render revision.

- [x] Commit SHA recorded.
- [x] `/ready` reports runtime and Firestore ready.
- [x] Intent Compiler telemetry uses `gemini-3.5-flash-lite`.
- [x] Planner telemetry uses `gemma-4-31b-it`.
- [x] Worker telemetry uses `gemma-4-31b-it`.
- [x] Standard run completes with exactly three successful model attempts.
- [x] Deliberate omission emits drift detection, deterministic repair, recheck, and final PASS.
- [x] Receipt evidence source is `simulator` / `logistics-v1`.
- [x] Firestore persists run, immutable contract, ordered events, telemetry, receipt, and validation.
- [ ] Dashboard screenshot shows hybrid routing and terminal integrity.
- [ ] Tool timeout fixture produces `UNKNOWN` evidence and terminal `BLOCKED`.
- [x] Backend tests, frontend tests, frontend build, and CI pass.

Production artifacts:

- Standard hybrid run: `hybrid-v3-standard.json`.
- Deliberate drift run: `hybrid-v3-drift.json`.

Do not begin benchmark work until every item is checked with real production artifacts.

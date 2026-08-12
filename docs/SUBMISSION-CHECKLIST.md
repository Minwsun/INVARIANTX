# Hackathon Submission Checklist

## Product

- [ ] Public GitHub repository points to the final commit.
- [ ] Render frontend URL loads without authentication.
- [ ] Backend `/health` returns success.
- [ ] Demo run completes drift, repair, recheck, tool execution, validation.
- [ ] Firestore persists runs, contracts, and events.
- [ ] Normal run stays within 2-3 LLM calls.
- [ ] Drift run stays within 4-5 LLM calls.

## Required Google Stack

- [ ] Gemini 3.5+ is visible in code and demo evidence.
- [ ] Google ADK 2.x Graph Workflow is visible in architecture and code.
- [ ] Render Blueprint deployment is live.
- [ ] Firestore persistence is live.

## Evidence

- [ ] README includes North Star, architecture, setup, evaluation, deployment.
- [ ] Architecture diagram is readable on GitHub.
- [ ] Evaluation baseline is committed.
- [ ] CI passes backend, frontend, evaluation, and static export checks.
- [ ] Demo video shows original intent, drift detection, repair, and completion.
- [ ] Submission text clearly says logistics is a demo use case.
- [ ] Screenshots avoid API keys, project secrets, and personal data.

## Security

- [ ] No `.env`, API key, service-account JSON, or credential is committed.
- [ ] GitHub Actions uses Workload Identity Federation.
- [ ] Render contains `GEMINI_API_KEY` and `GCP_SERVICE_ACCOUNT_JSON` secrets.
- [ ] Firestore service account has only `roles/datastore.user`.
- [ ] Backend CORS contains only the production frontend origin.
- [ ] Firestore client rules deny direct browser access.

## Final Smoke Test

```powershell
cd backend
pytest
python -m app.evaluation --output ..\benchmarks\baseline.json

cd ..\frontend
npm ci
npm run lint
$env:NEXT_PUBLIC_API_BASE_URL="https://BACKEND_URL"
npm run build
```

- [ ] Run demo once from a clean browser session.
- [ ] Confirm SSE reconnect/replay does not duplicate visible events.
- [ ] Confirm failed or blocked actions never appear as executed.
- [ ] Tag or record the submitted commit SHA.

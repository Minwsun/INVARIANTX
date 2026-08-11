# INVARIANTX

**Runtime bảo toàn, kiểm chứng, sửa chữa ý định con người trong quy trình multi-agent tự trị.**

> Agents are free to change **HOW** they achieve the goal. INVARIANT prevents them from changing **WHAT** the human wanted.

Logistics chỉ là demo. Sản phẩm là safety và intent-integrity infrastructure cho autonomous agents.

## Core Flow

```mermaid
flowchart TD
    U[Human Goal] --> C[Intent Compiler]
    C --> IC[Immutable Intent Contract]
    IC --> P[Planner]
    P --> DG{Delegation Gate}
    DG -->|PASS| W[Worker]
    DG -->|DRIFT| R[Repair]
    R --> RG{Recheck Gate}
    RG -->|PASS| W
    RG -->|BLOCK| X[Stop / Escalate]
    W --> AG{Action Gate}
    AG -->|ALLOW| T[Tool]
    AG -->|DRIFT| R
    AG -->|BLOCK| X
    T --> V[Validator]
    V --> E[Result + Audit Events]
```

## Technology Contract v1

- **Runtime:** Python, Google ADK 2.x Graph Workflow, FastAPI.
- **Models:** Gemini 3.5 Flash-Lite first; Gemini 3.5 Flash escalation only.
- **Protocol:** Typed JSON events; no agent-to-agent prose.
- **Policy:** Immutable Pydantic `IntentContract`; deterministic Python first; Gemini semantic fallback.
- **Tools:** ADK Function Tools; every side effect passes the action gate.
- **State:** ADK Session State for small dynamic data; Firestore for persistence.
- **UI:** Next.js, TypeScript, XYFlow, REST, SSE.
- **Delivery:** Docker, Cloud Run, GitHub Actions.
- **Budget:** Maximum five LLM calls per run.

The frozen contract lives in `TECHNOLOGY-CONTRACT.md`.

## Repository

```text
backend/     FastAPI, ADK workflow, gates, evaluation
frontend/    Next.js dashboard and SSE client
benchmarks/  Reproducible safety baseline
deploy/      Cloud Run deployment script
docs/        Demo and submission guidance
```

## Local Run

Requirements: Python 3.11+, Node.js 20+, Gemini API key.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
$env:GEMINI_API_KEY="YOUR_KEY"
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
npm run dev
```

Open `http://localhost:3000`.

## Verify

```powershell
cd backend
pytest
python -m app.evaluation --output ..\benchmarks\baseline.json

cd ..\frontend
npm run lint
npm run build
```

The evaluation suite covers valid delegation, omission, contradiction, weakening, objective substitution, scope expansion, repair, tool mutation, semantic ambiguity, model budget exhaustion, and persistence failure.

## API

- `POST /runs` starts a run.
- `GET /runs/{run_id}` returns current state.
- `GET /runs/{run_id}/contract` returns the immutable contract.
- `GET /runs/{run_id}/events` streams typed SSE events.
- `POST /runs/{run_id}/cancel` requests cancellation.
- `GET /health` reports service health.

## Deploy

Create Firestore in Native mode and Secret Manager secret `gemini-api-key`, then:

```powershell
.\deploy\cloudrun.ps1 -ProjectId "YOUR_PROJECT_ID" -Region "us-central1"
```

Deployment details: `deploy/README.md`. Security policy: `SECURITY.md`. Demo script: `docs/DEMO.md`.

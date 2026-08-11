# INVARIANT Dashboard

Next.js presentation layer for the INVARIANT runtime. It consumes FastAPI REST endpoints and the SSE event stream; it contains no gate or policy logic.

## Local Development

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://localhost:8000"
npm install
npm run dev
```

Open `http://localhost:3000` after starting the backend on port `8000`.

## Validation

```powershell
npm run lint
npm run build
```

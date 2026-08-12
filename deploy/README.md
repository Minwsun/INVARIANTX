# Render Deployment

INVARIANTX deploys through the root `render.yaml` Blueprint. The backend uses Render's native Python runtime; the frontend is a static site served from Render's CDN. Firestore remains the Google Cloud infrastructure service.

## 1. Prepare Firestore

Use an existing Google Cloud project with Firestore access:

```powershell
.\scripts\bootstrap-gcp.ps1 `
  -ProjectId "YOUR_PROJECT_ID" `
  -CreateKey
```

The command creates/reuses Firestore Native mode, creates `invariantx-render`, grants only `roles/datastore.user`, and writes a key under `.secrets/`. Never commit that directory.

## 2. Create Render Blueprint

1. Push the repository to GitHub.
2. In Render, choose **New → Blueprint**.
3. Select `Minwsun/INVARIANTX`.
4. Render detects `render.yaml` and creates the Python `invariantx-api` service plus static `invariantx-web` site.
5. Enter the prompted values:
   - `GOOGLE_CLOUD_PROJECT`: the project ID.
   - `GEMINI_API_KEY`: Gemini API key.
   - `GCP_SERVICE_ACCOUNT_JSON`: the complete JSON content from `.secrets/invariantx-render.json`.
   - `INVARIANT_DEMO_KEY`: a random secret used only by the protected drift proof endpoint.

The frontend receives the backend hostname through a Blueprint service reference. The backend CORS regex accepts only the generated `invariantx-web` Render hostname.

## 3. Verify

```powershell
.\scripts\verify-gcp.ps1 -ProjectId "YOUR_PROJECT_ID"
.\deploy\smoke-test.ps1 -BackendUrl "https://invariantx-api.onrender.com"
.\deploy\drift-smoke-test.ps1 `
  -BackendUrl "https://invariantx-api.onrender.com" `
  -DemoKey $env:INVARIANT_DEMO_KEY
```

Render Free services may cold-start. The smoke test allows 120 seconds by default.

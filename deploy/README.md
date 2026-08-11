# Cloud Run Deployment

## Prerequisites

- Google Cloud CLI authenticated with permission to manage Cloud Run, Artifact Registry, Firestore, APIs, and service accounts.
- Docker running.
- Firestore database created in Native mode.
- Secret Manager secret `gemini-api-key` containing the Gemini API key.
- Cloud Run runtime service account granted Firestore access and Secret Manager Secret Accessor.

## Deploy

```powershell
.\deploy\cloudrun.ps1 -ProjectId "YOUR_PROJECT_ID" -Region "us-central1"
```

The script builds and deploys backend first, injects its URL into the frontend build, deploys frontend, then restricts backend CORS to the frontend URL.

MVP uses `--max-instances 1` because live SSE wake-ups use an in-process condition. Firestore replay remains persistent. Multi-instance live fan-out requires a future shared notification service.

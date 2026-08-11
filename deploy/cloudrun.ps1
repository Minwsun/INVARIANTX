param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$Region = "us-central1",
    [string]$Repository = "invariantx",
    [string]$BackendService = "invariantx-api",
    [string]$FrontendService = "invariantx-web",
    [string]$GeminiSecret = "gemini-api-key"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is required. Install Google Cloud CLI, authenticate, then rerun."
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$registry = "$Region-docker.pkg.dev"
$backendImage = "$registry/$ProjectId/$Repository/backend:$((git -C $root rev-parse --short HEAD).Trim())"
$frontendImage = "$registry/$ProjectId/$Repository/frontend:$((git -C $root rev-parse --short HEAD).Trim())"

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com secretmanager.googleapis.com

$repositories = gcloud artifacts repositories list --location $Region --format "value(name)"
if ($repositories -notcontains $Repository) {
    gcloud artifacts repositories create $Repository --repository-format docker --location $Region
}

gcloud auth configure-docker $registry --quiet

docker build -t $backendImage (Join-Path $root "backend")
docker push $backendImage

gcloud run deploy $BackendService `
    --image $backendImage `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --max-instances 1 `
    --set-env-vars "INVARIANT_STORE=firestore" `
    --set-secrets "GEMINI_API_KEY=$GeminiSecret`:latest"

$backendUrl = (gcloud run services describe $BackendService --region $Region --format "value(status.url)").Trim()

docker build --build-arg "NEXT_PUBLIC_API_BASE_URL=$backendUrl" -t $frontendImage (Join-Path $root "frontend")
docker push $frontendImage

gcloud run deploy $FrontendService `
    --image $frontendImage `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --max-instances 1

$frontendUrl = (gcloud run services describe $FrontendService --region $Region --format "value(status.url)").Trim()

gcloud run services update $BackendService `
    --region $Region `
    --set-env-vars "INVARIANT_STORE=firestore,CORS_ORIGINS=$frontendUrl"

Write-Output "Backend:  $backendUrl"
Write-Output "Frontend: $frontendUrl"

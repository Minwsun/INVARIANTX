param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [Parameter(Mandatory = $true)]
    [string]$BillingAccount,
    [string]$Region = "asia-southeast1",
    [string]$Repository = "invariantx",
    [string]$RuntimeServiceAccount = "invariantx-runtime",
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
$serviceAccountEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
$backendImage = "$registry/$ProjectId/$Repository/backend:$((git -C $root rev-parse --short HEAD).Trim())"
$frontendImage = "$registry/$ProjectId/$Repository/frontend:$((git -C $root rev-parse --short HEAD).Trim())"
$frontendBuildConfig = Join-Path $root "deploy\cloudbuild.frontend.yaml"

gcloud config set project $ProjectId
& (Join-Path $root "scripts\verify-gcp.ps1") `
    -ProjectId $ProjectId `
    -BillingAccount $BillingAccount `
    -Region $Region `
    -RuntimeServiceAccount $RuntimeServiceAccount `
    -ArtifactRepository $Repository `
    -GeminiSecret $GeminiSecret

gcloud builds submit (Join-Path $root "backend") --tag=$backendImage

gcloud run deploy $BackendService `
    --image $backendImage `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --service-account=$serviceAccountEmail `
    --min-instances=0 `
    --max-instances 1 `
    --cpu=1 `
    --memory=512Mi `
    --set-env-vars "GOOGLE_CLOUD_PROJECT=$ProjectId,INVARIANT_STORE=firestore" `
    --set-secrets "GEMINI_API_KEY=$GeminiSecret`:latest"

$backendUrl = (gcloud run services describe $BackendService --region $Region --format "value(status.url)").Trim()

gcloud builds submit $root `
    --config=$frontendBuildConfig `
    --substitutions="_IMAGE=$frontendImage,_NEXT_PUBLIC_API_BASE_URL=$backendUrl"

gcloud run deploy $FrontendService `
    --image $frontendImage `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --min-instances=0 `
    --max-instances=2 `
    --cpu=1 `
    --memory=512Mi

$frontendUrl = (gcloud run services describe $FrontendService --region $Region --format "value(status.url)").Trim()

gcloud run services update $BackendService `
    --region $Region `
    --set-env-vars "INVARIANT_STORE=firestore,CORS_ORIGINS=$frontendUrl"

Write-Output "Backend:  $backendUrl"
Write-Output "Frontend: $frontendUrl"

& (Join-Path $PSScriptRoot "smoke-test.ps1") -BackendUrl $backendUrl

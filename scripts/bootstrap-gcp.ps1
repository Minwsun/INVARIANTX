param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$BillingAccount,
    [string]$ProjectName = "INVARIANTX",
    [string]$Region = "asia-southeast1",
    [string]$RuntimeServiceAccount = "invariantx-runtime",
    [string]$ArtifactRepository = "invariantx",
    [string]$GeminiSecret = "gemini-api-key",
    [decimal]$BudgetUsd = 10
)

$ErrorActionPreference = "Stop"

foreach ($command in "gcloud", "git", "python", "node") {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required"
    }
}

if (-not (gcloud auth list --filter=status:ACTIVE --format="value(account)")) {
    throw "Run 'gcloud auth login' first"
}

if (-not (gcloud projects describe $ProjectId --format="value(projectId)" 2>$null)) {
    gcloud projects create $ProjectId --name=$ProjectName
}

gcloud config set project $ProjectId
gcloud config set run/region $Region
gcloud config set artifacts/location $Region
gcloud billing projects link $ProjectId --billing-account=$BillingAccount

$budgetName = "INVARIANTX Hackathon Budget"
if (-not (gcloud billing budgets list --billing-account=$BillingAccount --filter="displayName='$budgetName'" --format="value(name)")) {
    gcloud billing budgets create `
        --billing-account=$BillingAccount `
        --display-name=$budgetName `
        --budget-amount="$($BudgetUsd)USD" `
        --filter-projects="projects/$ProjectId"
}

$apis = @(
    "run.googleapis.com",
    "firestore.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "apikeys.googleapis.com",
    "serviceusage.googleapis.com",
    "generativelanguage.googleapis.com"
)
gcloud services enable $apis

if (-not (gcloud firestore databases describe --database="(default)" --format="value(name)" 2>$null)) {
    gcloud firestore databases create `
        --database="(default)" `
        --location=$Region `
        --edition=standard `
        --type=firestore-native `
        --delete-protection
}

$serviceAccountEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"
if (-not (gcloud iam service-accounts describe $serviceAccountEmail --format="value(email)" 2>$null)) {
    gcloud iam service-accounts create $RuntimeServiceAccount --display-name="INVARIANTX Runtime"
}

foreach ($role in "roles/datastore.user", "roles/logging.logWriter") {
    gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$serviceAccountEmail" `
        --role=$role `
        --condition=None | Out-Null
}

if (-not (gcloud secrets describe $GeminiSecret --format="value(name)" 2>$null)) {
    $keyName = gcloud services api-keys create `
        --display-name="INVARIANTX Gemini" `
        --api-target="service=generativelanguage.googleapis.com" `
        --format="value(name)"
    $geminiKey = gcloud services api-keys get-key-string $keyName --format="value(keyString)"
    $tempPath = Join-Path $env:TEMP "invariantx-gemini-$PID.txt"
    try {
        [System.IO.File]::WriteAllText($tempPath, $geminiKey)
        gcloud secrets create $GeminiSecret --data-file=$tempPath
    }
    finally {
        if (Test-Path $tempPath) { Remove-Item -LiteralPath $tempPath -Force }
        $geminiKey = $null
    }
}

gcloud secrets add-iam-policy-binding $GeminiSecret `
    --member="serviceAccount:$serviceAccountEmail" `
    --role="roles/secretmanager.secretAccessor" | Out-Null

if (-not (gcloud artifacts repositories describe $ArtifactRepository --location=$Region --format="value(name)" 2>$null)) {
    gcloud artifacts repositories create $ArtifactRepository `
        --repository-format=docker `
        --location=$Region `
        --description="INVARIANTX container images"
}

& (Join-Path $PSScriptRoot "verify-gcp.ps1") `
    -ProjectId $ProjectId `
    -BillingAccount $BillingAccount `
    -Region $Region `
    -RuntimeServiceAccount $RuntimeServiceAccount `
    -ArtifactRepository $ArtifactRepository `
    -GeminiSecret $GeminiSecret

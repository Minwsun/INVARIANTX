param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$Location = "asia-southeast1",
    [string]$ServiceAccount = "invariantx-render",
    [switch]$CreateKey,
    [string]$KeyPath = ".secrets\invariantx-render.json"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is required"
}
if (-not (gcloud auth list --filter=status:ACTIVE --format="value(account)")) {
    throw "Run 'gcloud auth login' first"
}

gcloud projects describe $ProjectId | Out-Null
gcloud config set project $ProjectId
gcloud services enable firestore.googleapis.com iam.googleapis.com

if (-not (gcloud firestore databases describe --database="(default)" --format="value(name)" 2>$null)) {
    gcloud firestore databases create `
        --database="(default)" `
        --location=$Location `
        --edition=standard `
        --type=firestore-native `
        --delete-protection
}

$serviceAccountEmail = "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"
if (-not (gcloud iam service-accounts describe $serviceAccountEmail --format="value(email)" 2>$null)) {
    gcloud iam service-accounts create $ServiceAccount --display-name="INVARIANTX Render"
}

gcloud projects add-iam-policy-binding $ProjectId `
    --member="serviceAccount:$serviceAccountEmail" `
    --role="roles/datastore.user" `
    --condition=None | Out-Null

if ($CreateKey) {
    $resolvedKeyPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\$KeyPath"))
    $allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.secrets"))
    if (-not $resolvedKeyPath.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "KeyPath must stay inside the repository .secrets directory"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $resolvedKeyPath) | Out-Null
    if (Test-Path $resolvedKeyPath) { throw "key file already exists: $resolvedKeyPath" }
    gcloud iam service-accounts keys create $resolvedKeyPath --iam-account=$serviceAccountEmail
    Write-Output "Render secret GCP_SERVICE_ACCOUNT_JSON: paste the JSON from $resolvedKeyPath"
}

& (Join-Path $PSScriptRoot "verify-gcp.ps1") `
    -ProjectId $ProjectId `
    -ServiceAccount $ServiceAccount

param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [Parameter(Mandatory = $true)][string]$BillingAccount,
    [string]$Region = "asia-southeast1",
    [string]$RuntimeServiceAccount = "invariantx-runtime",
    [string]$ArtifactRepository = "invariantx",
    [string]$GeminiSecret = "gemini-api-key"
)

$ErrorActionPreference = "Stop"
$serviceAccountEmail = "$RuntimeServiceAccount@$ProjectId.iam.gserviceaccount.com"

gcloud projects describe $ProjectId | Out-Null
$billing = gcloud billing projects describe $ProjectId --format="value(billingAccountName,billingEnabled)"
if ($billing -notmatch $BillingAccount -or $billing -notmatch "True") { throw "billing is not active" }
gcloud firestore databases describe --database="(default)" | Out-Null
gcloud secrets describe $GeminiSecret | Out-Null
gcloud secrets versions describe latest --secret=$GeminiSecret | Out-Null
gcloud iam service-accounts describe $serviceAccountEmail | Out-Null
gcloud artifacts repositories describe $ArtifactRepository --location=$Region | Out-Null

$requiredApis = @(
    "run.googleapis.com",
    "firestore.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "generativelanguage.googleapis.com"
)
$enabledApis = gcloud services list --enabled --format="value(config.name)"
foreach ($api in $requiredApis) {
    if ($enabledApis -notcontains $api) { throw "required API is disabled: $api" }
}

Write-Output "GCP infrastructure verified: $ProjectId"

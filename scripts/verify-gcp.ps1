param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$ServiceAccount = "invariantx-render"
)

$ErrorActionPreference = "Stop"
$serviceAccountEmail = "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"

gcloud projects describe $ProjectId | Out-Null
gcloud firestore databases describe --database="(default)" | Out-Null
gcloud iam service-accounts describe $serviceAccountEmail | Out-Null

$enabledApis = gcloud services list --enabled --format="value(config.name)"
if ($enabledApis -notcontains "firestore.googleapis.com") {
    throw "required API is disabled: firestore.googleapis.com"
}

$policy = gcloud projects get-iam-policy $ProjectId `
    --flatten="bindings[].members" `
    --filter="bindings.role=roles/datastore.user AND bindings.members=serviceAccount:$serviceAccountEmail" `
    --format="value(bindings.role)"
if ($policy -ne "roles/datastore.user") { throw "service account lacks roles/datastore.user" }

Write-Output "Firestore infrastructure verified: $ProjectId"

param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$ServiceAccount = "invariantx-render",
    [string]$ConfirmServiceAccount,
    [switch]$DeleteServiceAccount
)

$ErrorActionPreference = "Stop"
$serviceAccountEmail = "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"

if (-not $DeleteServiceAccount) {
    Write-Output "Dry run only. Service account would be deleted: $serviceAccountEmail"
    Write-Output "The project and Firestore database are never deleted by this script."
    exit 0
}
if ($ConfirmServiceAccount -cne $serviceAccountEmail) {
    throw "ConfirmServiceAccount must exactly match $serviceAccountEmail"
}

gcloud iam service-accounts delete $serviceAccountEmail --quiet

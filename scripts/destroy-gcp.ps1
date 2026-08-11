param(
    [Parameter(Mandatory = $true)][string]$ProjectId,
    [string]$ConfirmProjectId,
    [switch]$DeleteProject
)

$ErrorActionPreference = "Stop"

if (-not $DeleteProject) {
    Write-Output "Dry run only. Project would be deleted: $ProjectId"
    Write-Output "Rerun with -DeleteProject -ConfirmProjectId '$ProjectId'"
    exit 0
}
if ($ConfirmProjectId -cne $ProjectId) {
    throw "ConfirmProjectId must exactly match ProjectId"
}

gcloud projects delete $ProjectId --quiet

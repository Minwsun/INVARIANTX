param(
    [Parameter(Mandatory = $true)][string]$BackendUrl,
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")
$health = Invoke-RestMethod "$BackendUrl/health"
if ($health.status -ne "ok") { throw "backend health check failed" }

$created = Invoke-RestMethod `
    -Method Post `
    -Uri "$BackendUrl/runs" `
    -ContentType "application/json" `
    -Body (@{ goal = "Reduce logistics cost by 15% without delaying medical orders." } | ConvertTo-Json)

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 2
    $run = Invoke-RestMethod "$BackendUrl/runs/$($created.run_id)"
} while ($run.status -notin @("COMPLETED", "BLOCKED", "FAILED", "CANCELLED") -and [DateTimeOffset]::UtcNow -lt $deadline)

if ($run.status -ne "COMPLETED") { throw "real run ended with status $($run.status): $($run.error)" }
if ($run.llm_call_count -gt 5) { throw "LLM call budget exceeded" }
if ($run.result.validation.verdict -ne "PASS") { throw "final contract validation failed" }
if ($run.result.validation.objective_status.PSObject.Properties.Value -contains $false) { throw "objective validation failed" }
if ($run.result.validation.constraint_status.PSObject.Properties.Value -contains $false) { throw "constraint validation failed" }
if (-not $run.result.tool_result.actual_metrics) { throw "execution receipt has no actual metrics" }
$contract = Invoke-RestMethod "$BackendUrl/runs/$($created.run_id)/contract"
if (-not $contract.objectives) { throw "compiled contract has no objectives" }

Write-Output "Smoke test passed: $($created.run_id), $($run.llm_call_count) LLM calls"

param(
    [Parameter(Mandatory = $true)][string]$BackendUrl,
    [Parameter(Mandatory = $true)][string]$DemoKey,
    [int]$TimeoutSeconds = 300,
    [string]$OutputPath = "artifacts/e2e/deliberate-drift.json"
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")
$headers = @{ "X-INVARIANT-DEMO-KEY" = $DemoKey }
$created = Invoke-RestMethod `
    -Method Post `
    -Uri "$BackendUrl/runs/demo" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body (@{ goal = "Reduce logistics cost by 15% without delaying medical orders." } | ConvertTo-Json)

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 2
    $run = Invoke-RestMethod "$BackendUrl/runs/$($created.run_id)"
} while ($run.status -notin @("COMPLETED", "BLOCKED", "FAILED", "CANCELLED") -and [DateTimeOffset]::UtcNow -lt $deadline)

if ($run.status -ne "COMPLETED") { throw "deliberate drift run ended with status $($run.status): $($run.error)" }
if ($run.scenario -ne "deliberate_constraint_omission") { throw "demo scenario missing" }
if ($run.repair_count -ne 1) { throw "expected exactly one repair" }
if ($run.llm_call_count -ne 3) { throw "expected exactly three LLM calls" }
if ($run.result.validation.verdict -ne "PASS") { throw "final validation failed" }

$contract = Invoke-RestMethod "$BackendUrl/runs/$($created.run_id)/contract"
$stream = Invoke-WebRequest "$BackendUrl/runs/$($created.run_id)/events"
$events = @(
    $stream.Content -split "`n`n" |
        Where-Object { $_ -match "data: " } |
        ForEach-Object {
            $dataLine = ($_ -split "`n" | Where-Object { $_ -like "data: *" })[0]
            ($dataLine.Substring(6) | ConvertFrom-Json)
        }
)
$types = @($events | ForEach-Object { $_.type })
$expected = @(
    "INTENT_COMPILED",
    "TASK_PROPOSED",
    "DEMO_DRIFT_INJECTED",
    "DRIFT_DETECTED",
    "REPAIR_ACCEPTED",
    "GATE_PASSED",
    "ACTION_PROPOSED",
    "TOOL_COMPLETED",
    "VALIDATION_COMPLETED",
    "RUN_COMPLETED"
)
$cursor = -1
foreach ($type in $expected) {
    $next = [Array]::IndexOf($types, $type, $cursor + 1)
    if ($next -lt 0) { throw "missing ordered event $type" }
    $cursor = $next
}

$report = [ordered]@{
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    commit_sha = (git rev-parse HEAD 2>$null)
    backend_url = $BackendUrl
    run_id = $created.run_id
    contract_id = $contract.id
    contract_version = $contract.version
    scenario = $run.scenario
    repair_count = $run.repair_count
    llm_call_count = $run.llm_call_count
    model_calls = $run.result.model_calls
    contract = $contract
    events = $events
    receipt = $run.result.tool_result
    validation = $run.result.validation
}
$directory = Split-Path -Parent $OutputPath
if ($directory) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
$report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "Deliberate drift proof passed: $($created.run_id), report $OutputPath"

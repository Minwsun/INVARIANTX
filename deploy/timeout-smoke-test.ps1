param(
    [Parameter(Mandatory = $true)][string]$BackendUrl,
    [Parameter(Mandatory = $true)][string]$DemoKey,
    [int]$TimeoutSeconds = 300,
    [string]$OutputPath = "docs/proof/hybrid-v3-tool-timeout.json"
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")
$headers = @{ "X-INVARIANT-DEMO-KEY" = $DemoKey }
$created = Invoke-RestMethod -Method Post -Uri "$BackendUrl/runs/demo/timeout" `
    -Headers $headers -ContentType "application/json" `
    -Body (@{ goal = "Reduce logistics cost by 15% without delaying medical orders." } | ConvertTo-Json)
$deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 2
    $run = Invoke-RestMethod "$BackendUrl/runs/$($created.run_id)"
} while ($run.status -notin @("COMPLETED", "BLOCKED", "FAILED", "CANCELLED") -and [DateTimeOffset]::UtcNow -lt $deadline)

if ($run.status -ne "BLOCKED") { throw "timeout run ended with status $($run.status)" }
if ($run.scenario -ne "deliberate_tool_timeout") { throw "timeout scenario missing" }
if ($run.result.tool_result.status -ne "unknown") { throw "receipt status is not UNKNOWN" }
if ($run.result.tool_result.evidence_source.type -ne "unknown") { throw "evidence type is not UNKNOWN" }
if ($run.result.tool_result.evidence_source.reference -ne "tool_timeout") { throw "timeout evidence missing" }

$report = [ordered]@{
    generated_at = [DateTimeOffset]::UtcNow.ToString("o")
    commit_sha = (git rev-parse HEAD 2>$null)
    backend_url = $BackendUrl
    run_id = $created.run_id
    scenario = $run.scenario
    status = $run.status
    llm_call_count = $run.llm_call_count
    model_calls = $run.result.model_calls
    receipt = $run.result.tool_result
    validation = $run.result.validation
}
$report | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "Tool timeout proof passed: $($created.run_id), report $OutputPath"

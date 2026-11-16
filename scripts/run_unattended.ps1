# Unattended runner: one plan Task per Claude session, retry until the plan is done.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\run_unattended.ps1
param(
    [string]$Plan = "docs/superpowers/plans/2026-11-15-viewer-readability.md",
    [string]$Model = "claude-opus-5-5",
    [int]$RetryMinutes = 15,     # wait after a session that made no progress
    [int]$MaxIdleRuns = 28,      # 28 x 15 min = 7 h, longer than one quota window
    [int]$MaxRuns = 60           # hard cap on productive sessions
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$plan = $Plan
$prompt = "Read docs/superpowers/plans/executor-prompt.md and follow it exactly. The plan is $Plan."
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "unattended.log"

function Write-Log([string]$text) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text
    $line | Tee-Object -FilePath $log -Append
}

# Count unchecked steps in the plan.
function Get-OpenSteps {
    return @(Select-String -Path $plan -Pattern '^- \[ \]').Count
}

$runs = 0
$idle = 0
while ($true) {
    if (Test-Path "STOP.md") { Write-Log "STOP.md found. Stopping."; break }
    $before = Get-OpenSteps
    if ($before -eq 0) { Write-Log "Plan complete."; break }
    if ($runs -ge $MaxRuns) { Write-Log "Reached MaxRuns ($MaxRuns). Stopping."; break }
    if ($idle -ge $MaxIdleRuns) { Write-Log "No progress in $idle consecutive sessions. Stopping."; break }

    Write-Log "Session start. Open steps: $before"
    claude -p $prompt --model $Model --permission-mode acceptEdits --allowedTools "Bash,PowerShell,Read,Edit,Write,Glob,Grep" |
        Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    $after = Get-OpenSteps
    Write-Log "Session end. Exit code: $code. Open steps: $after"

    if ($after -lt $before) {
        $runs++
        $idle = 0
    } else {
        # Usually the usage limit. Wait and try again.
        $idle++
        Write-Log "No progress. Waiting $RetryMinutes min (idle $idle/$MaxIdleRuns)."
        Start-Sleep -Seconds ($RetryMinutes * 60)
    }
}

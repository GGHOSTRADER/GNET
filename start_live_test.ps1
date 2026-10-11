[CmdletBinding()]
param(
    [switch]$SimulationConfirmed,
    [ValidateRange(1, 30)]
    [int]$DurationDays = 7,
    [ValidateRange(10, 3600)]
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not $SimulationConfirmed) {
    throw "The seven-day test is simulation-only. Re-run with -SimulationConfirmed after verifying the TradeStation account."
}
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "The pinned GNET runtime is missing at $pythonExe. Run .\install.ps1 first."
}

& (Join-Path $root "check_gnet_ports.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "GNET is not ready. Start .\launch_grid.ps1 and wait for all four ports before starting the test."
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $root "live_test_runs\$timestamp"
Write-Host "=== GNET seven-day simulation test ===" -ForegroundColor Cyan
Write-Host "Run directory: $runDir"
Write-Host "Keep this terminal open. Ctrl+C ends the observer without stopping GNET."
Write-Host "The observer never submits orders; TradeStation remains the execution authority."

Push-Location $root
try {
    & $pythonExe -m operations.live_test_monitor `
        --output-dir $runDir `
        --duration-days $DurationDays `
        --interval-seconds $IntervalSeconds
} finally {
    Pop-Location
}

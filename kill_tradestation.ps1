# Find and force-close TradeStation processes without touching unrelated apps.

param(
    [switch]$ListOnly
)

$ErrorActionPreference = "Stop"
$TRADESTATION_ROOTS = @(
    "C:\Program Files (x86)\TradeStation 10.0\",
    "C:\Program Files\TradeStation 10.0\"
)

function Get-TradeStationProcesses {
    $matches = @()
    foreach ($process in Get-Process) {
        $path = ""
        $company = ""
        try { $path = [string]$process.Path } catch { }
        try { $company = [string]$process.Company } catch { }
        $pathMatches = $false
        foreach ($root in $TRADESTATION_ROOTS) {
            if ($path.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
                $pathMatches = $true
                break
            }
        }
        if ($pathMatches -or $company -match "^TradeStation Technologies") {
            $matches += $process
        }
    }
    return @($matches | Sort-Object ProcessName, Id)
}

$targets = @(Get-TradeStationProcesses)
if ($targets.Count -eq 0) {
    Write-Host "No TradeStation processes are running." -ForegroundColor Green
    exit 0
}

Write-Host "TradeStation processes found:" -ForegroundColor Yellow
$targets | Select-Object ProcessName, Id, MainWindowTitle, Path | Format-Table -AutoSize

if ($ListOnly) {
    Write-Host "List-only mode: no processes were stopped." -ForegroundColor Cyan
    exit 0
}

foreach ($process in $targets) {
    Stop-Process -Id $process.Id -Force -ErrorAction Stop
    Write-Host "Killed $($process.ProcessName) PID $($process.Id)." -ForegroundColor Red
}

Start-Sleep -Seconds 1
$remaining = @(Get-TradeStationProcesses)
if ($remaining.Count -gt 0) {
    $details = $remaining | ForEach-Object { "$($_.ProcessName) PID $($_.Id)" }
    throw "TradeStation processes remain: $($details -join ', ')"
}

Write-Host "No TradeStation processes remain." -ForegroundColor Green

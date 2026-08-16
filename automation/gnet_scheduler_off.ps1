$ErrorActionPreference = "Stop"
$TaskName = "GNET Pipeline Watchdog"

if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "Task '$TaskName' is not installed."
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
Write-Host "GNET automatic startup and watchdog are OFF." -ForegroundColor Yellow
Write-Host "Already-running GNET services were left untouched; close them normally when finished."

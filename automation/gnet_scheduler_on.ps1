$ErrorActionPreference = "Stop"
$TaskName = "GNET Pipeline Watchdog"

if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "Task '$TaskName' is not installed. Run .\automation\install_gnet_scheduler.ps1 first."
}

Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
Write-Host "GNET automatic startup and watchdog are ON." -ForegroundColor Green

$ErrorActionPreference = "Stop"
$TaskName = "GNET Pipeline Watchdog"
$WatchdogPath = Join-Path $PSScriptRoot "gnet_watchdog.ps1"

if (-not (Test-Path -LiteralPath $WatchdogPath)) {
    throw "Watchdog script not found at $WatchdogPath"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WatchdogPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts and supervises the local GNET pipeline when explicitly enabled." `
    -Force `
    -ErrorAction Stop | Out-Null

Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
Write-Host "Installed '$TaskName' in the OFF state." -ForegroundColor Green
Write-Host "Run .\automation\gnet_scheduler_on.ps1 when automatic startup is wanted."

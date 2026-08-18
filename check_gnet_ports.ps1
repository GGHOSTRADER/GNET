# Check whether every TradeStation-facing GNET TCP service is listening.

param(
    [switch]$Watch,
    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"

$services = @(
    [pscustomobject]@{ Port = 9009; Service = "Bar TCP"; Module = "netwo_files.tcp_to_redis_connection" },
    [pscustomobject]@{ Port = 9010; Service = "Tick TCP"; Module = "netwo_files.tcp_to_redis_ticks" },
    [pscustomobject]@{ Port = 9011; Service = "Decision TCP"; Module = "inference.signal_tcp_server" },
    [pscustomobject]@{ Port = 9012; Service = "Candidate TCP"; Module = "inference.candidate_tcp_server" }
)

function Get-GnetPortStatus {
    $rows = foreach ($service in $services) {
        $listener = Get-NetTCPConnection `
            -State Listen `
            -LocalPort $service.Port `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1

        $processName = "-"
        $processId = $null
        if ($listener) {
            $processId = [int]$listener.OwningProcess
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                $processName = $process.ProcessName
            }
        }

        [pscustomobject]@{
            Status = if ($listener) { "LISTENING" } else { "MISSING" }
            Port = $service.Port
            Service = $service.Service
            Process = $processName
            PID = if ($null -ne $processId) { $processId } else { "-" }
            Module = $service.Module
        }
    }
    return $rows
}

function Show-GnetPortStatus {
    param([object[]]$Rows)

    Write-Host "=== GNET Live Port Monitor ===" -ForegroundColor Cyan
    Write-Host "Updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
    $Rows | Format-Table Status, Port, Service, Process, PID, Module -AutoSize | Out-Host

    $missing = @($Rows | Where-Object { $_.Status -eq "MISSING" })
    if ($missing.Count -eq 0) {
        Write-Host "READY: All four GNET endpoints are listening. TradeStation components may be enabled." -ForegroundColor Green
        return $true
    }

    $missingPorts = $missing.Port -join ", "
    Write-Host "NOT READY: Missing port(s): $missingPorts" -ForegroundColor Red
    Write-Host "Do not enable the GNET TradeStation indicators or strategy." -ForegroundColor Yellow
    return $false
}

if ($Watch) {
    try {
        $host.UI.RawUI.WindowTitle = "GNET Port Monitor"
    } catch {
        # Some non-interactive hosts do not expose a writable window title.
    }
    while ($true) {
        try {
            Clear-Host
        } catch {
            # Non-interactive hosts may not expose a screen buffer to clear.
        }
        [void](Show-GnetPortStatus -Rows @(Get-GnetPortStatus))
        Write-Host "`nRefreshing every $IntervalSeconds second(s). Press Ctrl+C to stop." -ForegroundColor DarkGray
        Start-Sleep -Seconds $IntervalSeconds
    }
}

$ready = Show-GnetPortStatus -Rows @(Get-GnetPortStatus)
if ($ready) {
    exit 0
}

Write-Host "Start or restart the pipeline with: .\restart.ps1" -ForegroundColor Yellow
exit 1

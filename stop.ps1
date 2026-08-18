# Stop GNET services started by launch.ps1 without clearing Redis data.

param(
    [switch]$StopTradeStation,
    [switch]$StopRedis,
    [switch]$StopDockerDesktop
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROCESS_REGISTRY = Join-Path $ROOT ".runtime\gnet_processes.json"
$GNET_PORTS = @(9009, 9010, 9011, 9012, 9020)

Write-Host "=== Stopping GNET ===" -ForegroundColor Cyan

$schedulerOff = Join-Path $ROOT "automation\gnet_scheduler_off.ps1"
if (Test-Path -LiteralPath $schedulerOff) {
    try {
        & $schedulerOff
    } catch {
        Write-Warning "Could not disable the watchdog: $($_.Exception.Message)"
    }
}

$processSnapshot = @()
try {
    $processSnapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
} catch {
    Write-Warning "Process-tree inspection is unavailable; recorded parent processes will still be stopped."
}

function Get-DescendantIds {
    param([int]$ParentId)
    $result = @()
    $children = @($processSnapshot | Where-Object { $_.ParentProcessId -eq $ParentId })
    foreach ($child in $children) {
        $result += Get-DescendantIds -ParentId $child.ProcessId
        $result += [int]$child.ProcessId
    }
    return $result
}

$records = @()
if (Test-Path -LiteralPath $PROCESS_REGISTRY) {
    try {
        $parsedRegistry = Get-Content -LiteralPath $PROCESS_REGISTRY -Raw | ConvertFrom-Json
        if ($parsedRegistry -is [System.Array]) {
            # Windows PowerShell 5 can preserve a top-level JSON array as one
            # nested pipeline object. Enumerate it explicitly so each service
            # record has one scalar PID.
            $records = @($parsedRegistry.GetEnumerator())
        } elseif ($null -ne $parsedRegistry) {
            $records = @($parsedRegistry)
        }
    } catch {
        Write-Warning "Could not read the GNET process registry: $($_.Exception.Message)"
    }
}

# Backward compatibility for service terminals launched before PID recording
# was added. Titles are assigned by launch.ps1 and narrowly identify GNET.
$knownTitlePattern = "^[1-9] \| (Decision TCP|Strategy Router|Candidate TCP|Tick Validator|Volume Profile|Transformer Features|Bar TCP|Tick TCP|Registry UI)"
$knownPids = @($records | ForEach-Object { [int]$_.pid })
$titledTerminals = @(
    Get-Process -Name "powershell" -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -match $knownTitlePattern }
)
foreach ($terminal in $titledTerminals) {
    if ($terminal.Id -notin $knownPids) {
        $records += [pscustomobject]@{
            pid = $terminal.Id
            title = $terminal.MainWindowTitle
            started_at = $terminal.StartTime.ToUniversalTime().ToString("o")
        }
    }
}

foreach ($record in $records) {
    $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
    if (-not $process) {
        continue
    }
    $recordedStart = [datetime]::Parse($record.started_at).ToUniversalTime()
    $actualStart = $process.StartTime.ToUniversalTime()
    if ([math]::Abs(($actualStart - $recordedStart).TotalSeconds) -gt 2) {
        Write-Warning "Skipping reused PID $($record.pid) for '$($record.title)'."
        continue
    }

    $descendants = @(Get-DescendantIds -ParentId $process.Id)
    foreach ($childId in $descendants) {
        Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped $($record.title) (PID $($record.pid))." -ForegroundColor Green
}

# Stop exact GNET module processes left by launches that predate PID tracking.
# The allowlist prevents unrelated Python and PowerShell processes from being touched.
$gnetModules = @(
    "inference.signal_tcp_server",
    "inference.strategy_router",
    "inference.candidate_tcp_server",
    "netwo_files.tick_validator",
    "feat_files.volume_profile",
    "feat_files.transformer_features",
    "netwo_files.tcp_to_redis_connection",
    "netwo_files.tcp_to_redis_ticks",
    "gnet_ui.server"
)
$escapedModules = $gnetModules | ForEach-Object { [regex]::Escape($_) }
$gnetModulePattern = "-m\s+(" + ($escapedModules -join "|") + ")(\s|$)"
$gnetMonitorPattern = "check_gnet_ports\.ps1.*\s-Watch(\s|$)"
$legacyProcesses = @(
    $processSnapshot |
        Where-Object {
            $isGnetModule =
                $_.Name -in @("python.exe", "pythonw.exe", "powershell.exe", "pwsh.exe") -and
                $_.CommandLine -match $gnetModulePattern
            $isPortMonitor =
                $_.Name -in @("powershell.exe", "pwsh.exe") -and
                $_.CommandLine -match $gnetMonitorPattern
            $isGnetModule -or $isPortMonitor
        } |
        Sort-Object { if ($_.Name -in @("python.exe", "pythonw.exe")) { 0 } else { 1 } }
)
foreach ($legacyProcess in $legacyProcesses) {
    $running = Get-Process -Id $legacyProcess.ProcessId -ErrorAction SilentlyContinue
    if ($running) {
        Stop-Process -Id $legacyProcess.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped auxiliary GNET process PID $($legacyProcess.ProcessId)." -ForegroundColor Green
    }
}

Start-Sleep -Milliseconds 750
$remainingListeners = @(
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in $GNET_PORTS }
)
if ($remainingListeners) {
    $details = $remainingListeners |
        Sort-Object LocalPort |
        ForEach-Object { "port $($_.LocalPort) PID $($_.OwningProcess)" }
    throw "GNET ports remain occupied: $($details -join ', '). Stop those processes manually."
}

if (Test-Path -LiteralPath $PROCESS_REGISTRY) {
    Remove-Item -LiteralPath $PROCESS_REGISTRY -Force
}

if ($StopTradeStation) {
    $tradeStationProcesses = @(Get-Process -Name "ORPlat" -ErrorAction SilentlyContinue)
    foreach ($process in $tradeStationProcesses) {
        if ($process.CloseMainWindow()) {
            Write-Host "Requested a graceful TradeStation close (PID $($process.Id))." -ForegroundColor Green
        } else {
            Write-Warning "TradeStation PID $($process.Id) has no closable main window; it was not forced closed."
        }
    }
}

if ($StopRedis -or $StopDockerDesktop) {
    docker stop redis1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stop Redis container redis1."
    }
    Write-Host "Stopped Redis container redis1; its stored data was not deleted." -ForegroundColor Green
}

if ($StopDockerDesktop) {
    Write-Host "Stopping Docker Desktop and its engine..." -ForegroundColor Yellow
    $dockerDesktopStopped = $false
    docker desktop stop | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $dockerDesktopStopped = $true
    } else {
        $dockerCli = Join-Path $env:ProgramFiles "Docker\Docker\DockerCli.exe"
        if (Test-Path -LiteralPath $dockerCli) {
            & $dockerCli -Shutdown
            if ($LASTEXITCODE -eq 0) {
                $dockerDesktopStopped = $true
            }
        }
    }
    if (-not $dockerDesktopStopped) {
        throw "GNET and Redis were stopped, but Docker Desktop did not accept a graceful shutdown command. Close it from the system tray."
    }
    Write-Host "Docker Desktop and its engine were stopped; Redis data was preserved." -ForegroundColor Green
}

Write-Host "=== GNET services stopped; Redis data preserved ===" -ForegroundColor Cyan

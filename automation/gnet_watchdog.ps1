param(
    [int]$CheckIntervalSeconds = 5,
    [int]$RestartCooldownSeconds = 30
)

$ErrorActionPreference = "Stop"
$GnetRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PythonExe = Join-Path $GnetRoot ".venv\Scripts\python.exe"
$GridLaunchScript = Join-Path $GnetRoot "launch_grid.ps1"
$LaunchScript = if (Test-Path -LiteralPath $GridLaunchScript) {
    $GridLaunchScript
} else {
    Join-Path $GnetRoot "launch.ps1"
}

$Services = @(
    @{ Key = "decision"; Name = "Decision TCP"; Module = "inference.signal_tcp_server"; Arguments = @("-m", "inference.signal_tcp_server") },
    @{ Key = "router"; Name = "Strategy Router"; Module = "inference.strategy_router"; Arguments = @("-m", "inference.strategy_router") },
    @{ Key = "candidate"; Name = "Candidate TCP"; Module = "inference.candidate_tcp_server"; Arguments = @("-m", "inference.candidate_tcp_server") },
    @{ Key = "validator"; Name = "Tick Validator"; Module = "netwo_files.tick_validator"; Arguments = @("-m", "netwo_files.tick_validator") },
    @{ Key = "volume_profile"; Name = "Volume Profile"; Module = "feat_files.volume_profile"; Arguments = @("-m", "feat_files.volume_profile", "--tick-size", "0.25", "--range-ticks", "600", "--snapshot-interval-s", "30", "--snapshot-offset-s", "29.925") },
    @{ Key = "transformer"; Name = "Transformer Features"; Module = "feat_files.transformer_features"; Arguments = @("-m", "feat_files.transformer_features") },
    @{ Key = "bar_tcp"; Name = "Bar TCP"; Module = "netwo_files.tcp_to_redis_connection"; Arguments = @("-m", "netwo_files.tcp_to_redis_connection") },
    @{ Key = "tick_tcp"; Name = "Tick TCP"; Module = "netwo_files.tcp_to_redis_ticks"; Arguments = @("-m", "netwo_files.tcp_to_redis_ticks") },
    @{ Key = "registry"; Name = "Registry UI"; Module = "gnet_ui.server"; Arguments = @("-m", "gnet_ui.server") }
)

function Test-GnetService {
    param([string]$Module)
    $needle = "-m $Module"
    $match = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($needle) } |
        Select-Object -First 1
    return $null -ne $match
}

function Start-GnetService {
    param([hashtable]$Service)
    $title = "GNET Watchdog | $($Service.Name)"
    $argumentText = ($Service.Arguments | ForEach-Object { "'$_'" }) -join " "
    $command = "Set-Location -LiteralPath '$GnetRoot'; `$host.UI.RawUI.WindowTitle = '$title'; & '$PythonExe' $argumentText"
    $windowsTerminal = (Get-Command wt.exe -ErrorAction SilentlyContinue).Source
    if ($windowsTerminal) {
        $serviceRunner = Join-Path $GnetRoot "automation\run_service_terminal.ps1"
        $arguments = @(
            "-w", "GNET", "new-tab",
            "--title", "Recovery | $($Service.Name)",
            "-d", $GnetRoot,
            "powershell.exe", "-NoProfile", "-NoExit", "-File", $serviceRunner,
            "-ServiceKey", $Service.Key
        )
        & $windowsTerminal @arguments | Out-Null
        Write-Host "[$(Get-Date -Format o)] restarted $($Service.Name) in the GNET Terminal window"
        return
    }
    Start-Process powershell -ArgumentList "-NoProfile", "-Command", $command | Out-Null
    Write-Host "[$(Get-Date -Format o)] restarted $($Service.Name)"
}

if (-not (Test-Path -LiteralPath $LaunchScript)) {
    throw "GNET launcher not found at $LaunchScript"
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "The packaged GNET Python runtime was not found at $PythonExe. Run .\install.ps1 first."
}

$anyServiceRunning = $false
foreach ($service in $Services) {
    if (Test-GnetService -Module $service.Module) {
        $anyServiceRunning = $true
        break
    }
}

if (-not $anyServiceRunning) {
    Write-Host "[$(Get-Date -Format o)] no GNET services detected; running $([IO.Path]::GetFileName($LaunchScript))"
    & $LaunchScript
    Start-Sleep -Seconds 10
}

$lastRestart = @{}
Write-Host "[$(Get-Date -Format o)] GNET watchdog active"

while ($true) {
    foreach ($service in $Services) {
        if (Test-GnetService -Module $service.Module) {
            continue
        }

        $now = Get-Date
        $previous = $lastRestart[$service.Module]
        if ($null -ne $previous -and ($now - $previous).TotalSeconds -lt $RestartCooldownSeconds) {
            continue
        }

        Start-GnetService -Service $service
        $lastRestart[$service.Module] = $now
    }
    Start-Sleep -Seconds $CheckIntervalSeconds
}

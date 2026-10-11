# Quoting-safe entry point for one GNET Windows Terminal pane.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "decision",
        "router",
        "candidate",
        "validator",
        "volume_profile",
        "transformer",
        "bar_tcp",
        "tick_tcp",
        "registry",
        "health_monitor"
    )]
    [string]$ServiceKey
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "The packaged GNET Python runtime was not found at $pythonExe. Run .\install.ps1 first."
}

$services = @{
    decision = @{
        Title = "1 | Decision TCP | port 9011"
        Arguments = @("-m", "inference.signal_tcp_server")
    }
    router = @{
        Title = "2 | Strategy Router"
        Arguments = @("-m", "inference.strategy_router")
    }
    candidate = @{
        Title = "3 | Candidate TCP | port 9012"
        Arguments = @("-m", "inference.candidate_tcp_server")
    }
    validator = @{
        Title = "4 | Tick Validator"
        Arguments = @("-m", "netwo_files.tick_validator")
    }
    volume_profile = @{
        Title = "5 | Volume Profile"
        Arguments = @(
            "-m", "feat_files.volume_profile",
            "--tick-size", "0.25",
            "--range-ticks", "600",
            "--snapshot-interval-s", "30",
            "--snapshot-offset-s", "29.925"
        )
    }
    transformer = @{
        Title = "6 | Transformer Features"
        Arguments = @("-m", "feat_files.transformer_features")
    }
    bar_tcp = @{
        Title = "7 | Bar TCP | port 9009"
        Arguments = @("-m", "netwo_files.tcp_to_redis_connection")
    }
    tick_tcp = @{
        Title = "8 | Tick TCP | port 9010"
        Arguments = @("-m", "netwo_files.tcp_to_redis_ticks")
    }
    registry = @{
        Title = "9 | Registry UI | port 9020"
        Arguments = @("-m", "gnet_ui.server")
    }
    health_monitor = @{
        Title = "10 | GNET Health Monitor | 10 sec"
        Script = "check_gnet_ports.ps1"
        Arguments = @("-Watch", "-IntervalSeconds", "10")
    }
}

$service = $services[$ServiceKey]
Set-Location -LiteralPath $root
$host.UI.RawUI.WindowTitle = $service.Title
Write-Host "=== $($service.Title) ===" -ForegroundColor Cyan
if ($service.Script) {
    $scriptPath = Join-Path $root $service.Script
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $scriptPath @($service.Arguments)
} else {
    & $pythonExe @($service.Arguments)
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Service exited with code $LASTEXITCODE." -ForegroundColor Red
}

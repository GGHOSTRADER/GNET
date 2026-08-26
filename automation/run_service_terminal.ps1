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
        "registry"
    )]
    [string]$ServiceKey
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

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
}

$service = $services[$ServiceKey]
Set-Location -LiteralPath $root
$host.UI.RawUI.WindowTitle = $service.Title
Write-Host "=== $($service.Title) ===" -ForegroundColor Cyan
& python @($service.Arguments)

if ($LASTEXITCODE -ne 0) {
    Write-Host "Service exited with code $LASTEXITCODE." -ForegroundColor Red
}

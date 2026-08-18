# Restart the complete GNET pipeline using the scoped stop and launch scripts.

param(
    [switch]$StopTradeStation,
    [switch]$RestartRedis
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $ROOT "stop.ps1") `
    -StopTradeStation:$StopTradeStation `
    -StopRedis:$RestartRedis

Set-Location -LiteralPath $ROOT
& (Join-Path $ROOT "launch.ps1")

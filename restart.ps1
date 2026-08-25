# Restart the complete GNET pipeline in the Windows Terminal grid.

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
& (Join-Path $ROOT "launch_grid.ps1")

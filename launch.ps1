# launch.ps1
# Full GNET pipeline launcher.
# Starts Docker, Redis, TradeStation, then opens all 7 Python services
# each in its own visible PowerShell terminal (numbered in the title bar).

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== GNET Launch Script ===" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1) Docker Desktop
# ---------------------------------------------------------------------------
Write-Host "`n[1/4] Starting Docker Desktop..." -ForegroundColor Yellow
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

Write-Host "      Waiting for Docker engine (up to 60s)..." -ForegroundColor Gray
$elapsed = 0
do {
    Start-Sleep -Seconds 3
    $elapsed += 3
    docker ps | Out-Null
} while ($LASTEXITCODE -ne 0 -and $elapsed -lt 60)

if ($LASTEXITCODE -ne 0) {
    Write-Host "      ERROR: Docker engine did not start in time." -ForegroundColor Red
    exit 1
}
Write-Host "      Docker engine ready." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2) Redis container
# ---------------------------------------------------------------------------
Write-Host "`n[2/4] Starting Redis container (redis1)..." -ForegroundColor Yellow
docker start redis1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      ERROR: Failed to start redis1. Create it first:" -ForegroundColor Red
    Write-Host "      docker run -d --name redis1 -p 6381:6379 redis" -ForegroundColor Gray
    exit 1
}
Write-Host "      Redis running on 127.0.0.1:6381" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3) TradeStation
# ---------------------------------------------------------------------------
Write-Host "`n[3/4] Launching TradeStation..." -ForegroundColor Yellow
Start-Process "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\TradeStation\TradeStation.lnk"
Write-Host "      TradeStation launched." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4) Python service terminals (in pipeline order)
# ---------------------------------------------------------------------------
Write-Host "`n[4/4] Opening Python service terminals..." -ForegroundColor Yellow

function Open-Terminal {
    param([string]$Title, [string]$Command)
    $cmd = "cd '$ROOT'; `$host.UI.RawUI.WindowTitle = '$Title'; $Command"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}

# Bar data:  TS -> BarBridge.dll  -> port 9009 -> Redis (validated_bar)
Open-Terminal -Title "1 | Bar TCP         | port 9009" `
              -Command "python -m netwo_files.tcp_to_redis_connection"
Start-Sleep -Seconds 1

# Tick data: TS -> TickBridge.dll -> port 9010 -> Redis (tick_data_raw -> tick_data_validated)
Open-Terminal -Title "2 | Tick TCP        | port 9010" `
              -Command "python -m netwo_files.tcp_to_redis_ticks"
Start-Sleep -Seconds 1

Open-Terminal -Title "3 | Tick Validator" `
              -Command "python -m netwo_files.tick_validator"
Start-Sleep -Seconds 1

Open-Terminal -Title "4 | Volume Profile" `
              -Command "python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30"
Start-Sleep -Seconds 1

# Feature + inference: validated_bar -> transformer -> inference -> signal_tcp -> TS
Open-Terminal -Title "5 | Transformer Features" `
              -Command "python -m feat_files.transformer_features"
Start-Sleep -Seconds 2

Open-Terminal -Title "6 | Inference Engine" `
              -Command "python -m inference.inference_engine"
Start-Sleep -Seconds 3

Open-Terminal -Title "7 | Signal TCP      | port 9011" `
              -Command "python -m inference.signal_tcp_server"

Write-Host "`n=== All services launched ===" -ForegroundColor Cyan
Write-Host "   7 terminal windows open (numbered 1-7 in the title bar)." -ForegroundColor White
Write-Host "   Apply EasyLanguage indicators in TradeStation once it finishes loading." -ForegroundColor White

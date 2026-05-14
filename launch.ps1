# launch.ps1
# Launches Docker Desktop, starts Redis container, and opens TradeStation

Write-Host "=== GNET Launch Script ===" -ForegroundColor Cyan

# 1) Launch Docker Desktop
Write-Host "`n[1/3] Starting Docker Desktop..." -ForegroundColor Yellow
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# Wait for Docker engine to be ready
Write-Host "      Waiting for Docker engine..." -ForegroundColor Gray
$timeout = 60
$elapsed = 0
do {
    Start-Sleep -Seconds 3
    $elapsed += 3
    $ready = docker ps 2>$null
} while ($LASTEXITCODE -ne 0 -and $elapsed -lt $timeout)

if ($LASTEXITCODE -ne 0) {
    Write-Host "      ERROR: Docker engine did not start in time. Exiting." -ForegroundColor Red
    exit 1
}
Write-Host "      Docker engine ready." -ForegroundColor Green

# 2) Start Redis container
Write-Host "`n[2/3] Starting Redis container (redis1)..." -ForegroundColor Yellow
docker start redis1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      ERROR: Failed to start redis1. Is the container created?" -ForegroundColor Red
    Write-Host "      Run: docker run -d --name redis1 -p 6381:6379 redis" -ForegroundColor Gray
    exit 1
}
Write-Host "      Redis running on 127.0.0.1:6381" -ForegroundColor Green

# 3) Launch TradeStation
Write-Host "`n[3/3] Launching TradeStation..." -ForegroundColor Yellow
Start-Process "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\TradeStation\TradeStation.lnk"
Write-Host "      TradeStation launched." -ForegroundColor Green

Write-Host "`n=== Done. Now start the Python TCP server in a new terminal: ===" -ForegroundColor Cyan
Write-Host "      python -m netwo_files.tcp_to_redis_connection" -ForegroundColor White
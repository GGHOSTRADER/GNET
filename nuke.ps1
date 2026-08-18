# Hard-reset GNET Redis. This permanently removes the redis1 container and data.

param(
    [switch]$ConfirmDataLoss,
    [switch]$RecreateEmptyRedis
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$CONTAINER_NAME = "redis1"

if (-not $ConfirmDataLoss) {
    throw @"
DESTRUCTIVE OPERATION REFUSED.
This command permanently removes container '$CONTAINER_NAME' and every Redis
stream, consumer group, pending entry, offset, and readiness key stored in it.
Run .\nuke.ps1 -ConfirmDataLoss only when a complete GNET Redis reset is intended.
"@
}

Write-Host "=== GNET HARD RESET ===" -ForegroundColor Red
Write-Host "Stopping GNET services before removing Redis..." -ForegroundColor Yellow
& (Join-Path $ROOT "stop.ps1")

$containerId = docker ps -aq --filter "name=^/$CONTAINER_NAME$"
if ($LASTEXITCODE -ne 0) {
    throw "Docker could not query container '$CONTAINER_NAME'. Is Docker Desktop running?"
}

if ($containerId) {
    $resolvedName = docker inspect --format "{{.Name}}" $containerId
    if ($LASTEXITCODE -ne 0 -or $resolvedName -ne "/$CONTAINER_NAME") {
        throw "Safety check failed: Docker target is not exactly '/$CONTAINER_NAME'."
    }
    docker rm -f $CONTAINER_NAME | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove Docker container '$CONTAINER_NAME'."
    }
    Write-Host "Removed '$CONTAINER_NAME' and all Redis data stored inside it." -ForegroundColor Red
} else {
    Write-Host "Container '$CONTAINER_NAME' does not exist; nothing was removed." -ForegroundColor Yellow
}

if ($RecreateEmptyRedis) {
    docker run -d --name $CONTAINER_NAME -p 6381:6379 redis | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Container removal succeeded, but fresh '$CONTAINER_NAME' creation failed."
    }
    Write-Host "Created a fresh empty '$CONTAINER_NAME' on 127.0.0.1:6381." -ForegroundColor Green
}

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
    throw "Redis was reset, but Docker Desktop did not accept a graceful shutdown command. Close it from the system tray."
}

Write-Host "Docker Desktop and its engine were stopped." -ForegroundColor Green
Write-Host "Other containers were stopped by the engine shutdown but were not removed." -ForegroundColor Cyan
Write-Host "=== HARD RESET COMPLETE ===" -ForegroundColor Red

# launch.ps1
# Full GNET pipeline launcher.
# Starts Docker and Redis, opens all 9 Python services in race-safe order,
# then launches TradeStation only after every TCP listener is ready.

param([switch]$Grid)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$DOCKER_DESKTOP = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$TRADESTATION_SHORTCUT = "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\TradeStation\TradeStation.lnk"
$ROUTER_READY_KEY = "gnet:strategy_router:ready"
$RUNTIME_DIR = Join-Path $ROOT ".runtime"
$PROCESS_REGISTRY = Join-Path $RUNTIME_DIR "gnet_processes.json"
$script:ManagedProcesses = @()
$script:GridServiceIndex = 0
$script:WindowsTerminal = $null

function Save-ProcessRegistry {
    $script:ManagedProcesses | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $PROCESS_REGISTRY -Encoding UTF8
}

function Register-ManagedProcess {
    param([System.Diagnostics.Process]$Process, [string]$Title)
    $script:ManagedProcesses += [pscustomobject]@{
        pid = $Process.Id
        title = $Title
        started_at = $Process.StartTime.ToUniversalTime().ToString("o")
    }
    Save-ProcessRegistry
}

function Open-Terminal {
    param([string]$Title, [string]$Command, [string]$ServiceKey)
    $cmd = "cd '$ROOT'; `$host.UI.RawUI.WindowTitle = '$Title'; $Command"
    if ($Grid) {
        $serviceRunner = Join-Path $ROOT "automation\run_service_terminal.ps1"
        $tabTitles = @("Strategy", "Tick Pipeline", "Bar and Operations")
        $position = $script:GridServiceIndex % 3
        $tabIndex = [math]::Floor($script:GridServiceIndex / 3)
        if ($position -eq 0) {
            $arguments = @(
                "-w", "GNET", "new-tab",
                "--title", $tabTitles[$tabIndex],
                "-d", $ROOT,
                "powershell.exe", "-NoProfile", "-NoExit", "-File", $serviceRunner,
                "-ServiceKey", $ServiceKey
            )
        } else {
            $paneSize = if ($position -eq 1) { "0.666" } else { "0.5" }
            $arguments = @(
                "-w", "GNET", "split-pane", "-V", "--size", $paneSize,
                "--title", $Title,
                "-d", $ROOT,
                "powershell.exe", "-NoProfile", "-NoExit", "-File", $serviceRunner,
                "-ServiceKey", $ServiceKey
            )
        }
        & $script:WindowsTerminal @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Windows Terminal failed to open '$Title'."
        }
        $script:GridServiceIndex += 1
        Start-Sleep -Milliseconds 350
        return
    }
    $process = Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd -PassThru
    Register-ManagedProcess -Process $process -Title $Title
}

function Wait-ListeningPort {
    param([int]$Port, [int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        if ($listener) {
            Write-Host "      Port $Port is listening." -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for TCP port $Port. Check the service terminal for errors."
}

function Wait-Redis {
    param([int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $reply = docker exec redis1 redis-cli ping 2>$null
        if ($reply -eq "PONG") {
            Write-Host "      Redis answered PING." -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Redis container started but did not answer PING within $TimeoutSeconds seconds."
}

function Wait-Router {
    param([int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $ready = docker exec redis1 redis-cli get $ROUTER_READY_KEY 2>$null
        if ($ready -eq "1") {
            Write-Host "      Strategy router loaded its model and is reading Redis." -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Strategy router did not become ready. Check its terminal for model or configuration errors."
}

function Wait-HttpEndpoint {
    param([string]$Url, [int]$TimeoutSeconds = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "      Registry UI is responding at $Url" -ForegroundColor Green
                return
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    } while ((Get-Date) -lt $deadline)
    throw "Registry UI did not respond at $Url. Check its service terminal for errors."
}

Write-Host "=== GNET Launch Script ===" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1) Docker Desktop
# ---------------------------------------------------------------------------
Write-Host "`n[1/4] Starting Docker Desktop..." -ForegroundColor Yellow
if (-not (Test-Path -LiteralPath $DOCKER_DESKTOP)) {
    throw "Docker Desktop was not found at $DOCKER_DESKTOP"
}
Start-Process $DOCKER_DESKTOP

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
Wait-Redis

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH. Activate the GNET environment first."
}
if ($Grid) {
    $script:WindowsTerminal = (Get-Command wt.exe -ErrorAction SilentlyContinue).Source
    if (-not $script:WindowsTerminal) {
        throw "Windows Terminal (wt.exe) is required for -Grid mode."
    }
}

$occupiedPorts = @(9009, 9010, 9011, 9012) | Where-Object {
    Get-NetTCPConnection -State Listen -LocalPort $_ -ErrorAction SilentlyContinue
}
if ($occupiedPorts.Count -gt 0) {
    throw "Cannot launch: TCP port(s) $($occupiedPorts -join ', ') are already in use. Stop the existing GNET services first."
}

# ---------------------------------------------------------------------------
# 3) Python service terminals (consumers before producers)
# ---------------------------------------------------------------------------
if ($Grid) {
    Write-Host "`n[3/4] Opening one Windows Terminal grid..." -ForegroundColor Yellow
} else {
    Write-Host "`n[3/4] Opening Python service terminals..." -ForegroundColor Yellow
}
New-Item -ItemType Directory -Path $RUNTIME_DIR -Force | Out-Null
$script:ManagedProcesses = @()
Save-ProcessRegistry

# Decision return path must listen before any candidate can be processed.
Open-Terminal -Title "1 | Decision TCP     | port 9011" `
              -Command "python -m inference.signal_tcp_server" `
              -ServiceKey "decision"
Wait-ListeningPort -Port 9011

# Router must subscribe before feature or candidate producers begin.
docker exec redis1 redis-cli del $ROUTER_READY_KEY | Out-Null
Open-Terminal -Title "2 | Strategy Router" `
              -Command "python -m inference.strategy_router" `
              -ServiceKey "router"
Wait-Router

Open-Terminal -Title "3 | Candidate TCP    | port 9012" `
              -Command "python -m inference.candidate_tcp_server" `
              -ServiceKey "candidate"
Wait-ListeningPort -Port 9012

# Tick services occupy one tab; consumers start before the TCP producer.
Open-Terminal -Title "4 | Tick Validator" `
              -Command "python -m netwo_files.tick_validator" `
              -ServiceKey "validator"
Start-Sleep -Seconds 1

Open-Terminal -Title "5 | Volume Profile" `
              -Command "python -m feat_files.volume_profile --tick-size 0.25 --range-ticks 600 --snapshot-interval-s 30" `
              -ServiceKey "volume_profile"
Start-Sleep -Seconds 1

Open-Terminal -Title "8 | Tick TCP         | port 9010" `
              -Command "python -m netwo_files.tcp_to_redis_ticks" `
              -ServiceKey "tick_tcp"
Wait-ListeningPort -Port 9010

# Bar and transformer services occupy the final tab. The router is already
# subscribed before the feature producer starts.
Open-Terminal -Title "6 | Transformer Features" `
              -Command "python -m feat_files.transformer_features" `
              -ServiceKey "transformer"
Start-Sleep -Seconds 1

Open-Terminal -Title "7 | Bar TCP          | port 9009" `
              -Command "python -m netwo_files.tcp_to_redis_connection" `
              -ServiceKey "bar_tcp"
Wait-ListeningPort -Port 9009

$registryUrl = "http://127.0.0.1:9020/api/strategies"
try {
    $existingRegistry = Invoke-WebRequest -Uri $registryUrl -UseBasicParsing -TimeoutSec 2
} catch {
    $existingRegistry = $null
}
if ($existingRegistry.StatusCode -ne 200) {
    Open-Terminal -Title "9 | Registry UI      | port 9020" `
                  -Command "python -m gnet_ui.server" `
                  -ServiceKey "registry"
} else {
    $registryListener = Get-NetTCPConnection -State Listen -LocalPort 9020 -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($registryListener) {
        $registryProcess = Get-Process -Id $registryListener.OwningProcess -ErrorAction SilentlyContinue
        if ($registryProcess) {
            Register-ManagedProcess -Process $registryProcess -Title "9 | Existing Registry UI | port 9020"
        }
    }
}
Wait-HttpEndpoint -Url $registryUrl

# ---------------------------------------------------------------------------
# 4) TradeStation -- last, after every listener and consumer is ready
# ---------------------------------------------------------------------------
Write-Host "`n[4/4] Launching TradeStation..." -ForegroundColor Yellow
if (-not (Test-Path -LiteralPath $TRADESTATION_SHORTCUT)) {
    throw "TradeStation shortcut was not found at $TRADESTATION_SHORTCUT"
}
Start-Process $TRADESTATION_SHORTCUT
Write-Host "      TradeStation launched." -ForegroundColor Green
Start-Process "http://127.0.0.1:9020"

Write-Host "`n=== All services launched ===" -ForegroundColor Cyan
if ($Grid) {
    Write-Host "   One GNET Windows Terminal window contains 3 tabs with 3 panes each." -ForegroundColor White
} else {
    Write-Host "   Up to 9 service terminals are open; an existing registry UI is reused." -ForegroundColor White
}
Write-Host "   Model registry: http://127.0.0.1:9020" -ForegroundColor White
Write-Host "   Apply EasyLanguage indicators in TradeStation once it finishes loading." -ForegroundColor White

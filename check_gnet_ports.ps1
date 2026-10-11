# Check whether every TradeStation-facing GNET TCP service is listening.

param(
    [switch]$Watch,
    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"

$tradeStationProcessNames = @(
    "ORPlat", "orchart", "ORCAL", "ORCLPrxy", "ORDllHst", "WHServer",
    "TSDev", "TradeStationAgentForms", "TSLoggerService", "TsRTAServer", "TSScanner"
)
$memoryLogDirectory = Join-Path $PSScriptRoot "memory_logs"
$memoryLogPath = Join-Path $memoryLogDirectory (
    "gnet_health_memory_{0}.csv" -f (Get-Date -Format "yyyyMMdd_HHmmss")
)
$script:lastMemoryLogAt = [datetime]::MinValue

$services = @(
    [pscustomobject]@{ Port = 9009; Service = "Bar TCP"; Module = "netwo_files.tcp_to_redis_connection" },
    [pscustomobject]@{ Port = 9010; Service = "Tick TCP"; Module = "netwo_files.tcp_to_redis_ticks" },
    [pscustomobject]@{ Port = 9011; Service = "Decision TCP"; Module = "inference.signal_tcp_server" },
    [pscustomobject]@{ Port = 9012; Service = "Candidate TCP"; Module = "inference.candidate_tcp_server" }
)

function Get-GnetPortStatus {
    $rows = foreach ($service in $services) {
        $listener = Get-NetTCPConnection `
            -State Listen `
            -LocalPort $service.Port `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1

        $processName = "-"
        $processId = $null
        if ($listener) {
            $processId = [int]$listener.OwningProcess
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                $processName = $process.ProcessName
            }
        }

        [pscustomobject]@{
            Status = if ($listener) { "LISTENING" } else { "MISSING" }
            Port = $service.Port
            Service = $service.Service
            Process = $processName
            PID = if ($null -ne $processId) { $processId } else { "-" }
            Module = $service.Module
        }
    }
    return $rows
}

function Get-LatestRedisEntry {
    param([Parameter(Mandatory = $true)][string]$Stream)

    try {
        $lines = @(& docker exec redis1 redis-cli --raw XREVRANGE $Stream + - COUNT 1 2>$null)
        if ($LASTEXITCODE -ne 0 -or $lines.Count -lt 1) {
            return $null
        }
        $entryId = [string]$lines[0]
        $fields = @{}
        for ($index = 1; $index + 1 -lt $lines.Count; $index += 2) {
            $fields[[string]$lines[$index]] = [string]$lines[$index + 1]
        }
        $redisTimeMs = [int64]($entryId.Split("-")[0])
        $ageSeconds = [math]::Max(
            0,
            ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - $redisTimeMs) / 1000.0
        )
        return [pscustomobject]@{
            Id = $entryId
            Fields = $fields
            AgeSeconds = [math]::Round($ageSeconds, 1)
        }
    } catch {
        return $null
    }
}

function Get-GnetOperationalStatus {
    $tsProcesses = @(
        Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $tradeStationProcessNames -contains $_.ProcessName }
    )
    $orPlat = $tsProcesses | Where-Object ProcessName -EQ "ORPlat" | Select-Object -First 1
    $dockerDesktop = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $dockerBackend = Get-Process -Name "com.docker.backend" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $dockerEngineReady = $false
    $redisContainerStatus = "unavailable"
    $redisPing = $false
    try {
        $dockerInfo = @(& docker info --format "{{.ServerVersion}}" 2>$null)
        $dockerEngineReady = $LASTEXITCODE -eq 0 -and $dockerInfo.Count -gt 0
        if ($dockerEngineReady) {
            $redisStatusLines = @(& docker inspect redis1 --format "{{.State.Status}}" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $redisStatusLines.Count -gt 0) {
                $redisContainerStatus = ([string]$redisStatusLines[0]).Trim()
            } else {
                $redisContainerStatus = "missing"
            }
            if ($redisContainerStatus -eq "running") {
                $pingLines = @(& docker exec redis1 redis-cli --raw PING 2>$null)
                $redisPing = $LASTEXITCODE -eq 0 -and $pingLines.Count -gt 0 -and
                    ([string]$pingLines[0]).Trim() -eq "PONG"
            }
        }
    } catch {
        $dockerEngineReady = $false
        $redisContainerStatus = "unavailable"
        $redisPing = $false
    }
    $barEntry = Get-LatestRedisEntry -Stream "validated_bar"
    $featureEntry = Get-LatestRedisEntry -Stream "features_transformer"

    $routerReady = $false
    try {
        $routerValue = (& docker exec redis1 redis-cli --raw GET gnet:strategy_router:ready 2>$null).Trim()
        $routerReady = $LASTEXITCODE -eq 0 -and $routerValue -eq "1"
    } catch {
        $routerReady = $false
    }

    $liveTestActive = $false
    try {
        $liveTestActive = $null -ne (Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
            Where-Object CommandLine -Match "operations\.live_test_monitor" |
            Select-Object -First 1)
    } catch {
        $liveTestActive = $false
    }

    $availableRamMb = $null
    try {
        $availableRamMb = [math]::Round(
            (Get-Counter "\Memory\Available MBytes").CounterSamples[0].CookedValue,
            0
        )
    } catch {
        # Memory counters can be unavailable briefly during Windows startup.
    }

    $privateMemoryMb = if ($orPlat) {
        [math]::Round($orPlat.PrivateMemorySize64 / 1MB, 1)
    } else {
        $null
    }
    $mode = if ($barEntry -and $barEntry.Fields.ContainsKey("ingest_mode")) {
        $barEntry.Fields["ingest_mode"]
    } else {
        "unknown"
    }

    $snapshot = [pscustomobject]@{
        TradeStationAlive = $null -ne $orPlat
        TradeStationResponding = $null -ne $orPlat -and $orPlat.Responding
        TradeStationPrivateMb = $privateMemoryMb
        DockerDesktopAlive = $null -ne $dockerDesktop
        DockerBackendAlive = $null -ne $dockerBackend
        DockerEngineReady = $dockerEngineReady
        RedisContainerStatus = $redisContainerStatus
        RedisPing = $redisPing
        SystemAvailableRamMb = $availableRamMb
        IngestMode = $mode
        LastValidatedBarAgeSeconds = if ($barEntry) { $barEntry.AgeSeconds } else { $null }
        LastTransformerFeatureAgeSeconds = if ($featureEntry) { $featureEntry.AgeSeconds } else { $null }
        RouterReady = $routerReady
        LiveTestObserverActive = $liveTestActive
    }

    if (((Get-Date) - $script:lastMemoryLogAt).TotalSeconds -ge 600) {
        New-Item -ItemType Directory -Path $memoryLogDirectory -Force | Out-Null
        [pscustomobject]@{
            timestamp = (Get-Date).ToString("o")
            tradestation_private_mb = $snapshot.TradeStationPrivateMb
            system_available_ram_mb = $snapshot.SystemAvailableRamMb
            tradestation_alive = $snapshot.TradeStationAlive
            tradestation_responding = $snapshot.TradeStationResponding
        } | Export-Csv -LiteralPath $memoryLogPath -Append -NoTypeInformation
        $script:lastMemoryLogAt = Get-Date
    }

    return $snapshot
}

function Write-StatusLine {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][ValidateSet("Healthy", "Failed", "Missing", "Neutral")][string]$State
    )

    $color = switch ($State) {
        "Healthy" { "Green" }
        "Failed" { "Red" }
        "Missing" { "Yellow" }
        default { "Gray" }
    }
    Write-Host ($Label.PadRight(27)) -NoNewline
    Write-Host $Value -ForegroundColor $color
}

function Show-GnetPortStatus {
    param([object[]]$Rows)

    Write-Host "=== GNET Operational Dashboard ===" -ForegroundColor Cyan
    Write-Host "Updated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host ("{0,-10} {1,-5} {2,-14} {3,-10} {4,-8} {5}" -f "Status", "Port", "Service", "Process", "PID", "Module")
    Write-Host ("{0,-10} {1,-5} {2,-14} {3,-10} {4,-8} {5}" -f "------", "----", "-------", "-------", "---", "------")
    foreach ($row in $Rows) {
        $portColor = if ($row.Status -eq "LISTENING") { "Green" } else { "Yellow" }
        Write-Host ("{0,-10}" -f $row.Status) -ForegroundColor $portColor -NoNewline
        Write-Host (" {0,-5} {1,-14} {2,-10} {3,-8} {4}" -f $row.Port, $row.Service, $row.Process, $row.PID, $row.Module)
    }
    Write-Host ""

    $operational = Get-GnetOperationalStatus
    $barAge = if ($null -eq $operational.LastValidatedBarAgeSeconds) { "missing" } else { "$($operational.LastValidatedBarAgeSeconds) s ago" }
    $featureAge = if ($null -eq $operational.LastTransformerFeatureAgeSeconds) { "missing" } else { "$($operational.LastTransformerFeatureAgeSeconds) s ago" }
    $availableRam = if ($null -eq $operational.SystemAvailableRamMb) { "unavailable" } else { "$($operational.SystemAvailableRamMb) MB" }

    $tradeStationRam = if ($null -eq $operational.TradeStationPrivateMb) { "n/a" } else { "$($operational.TradeStationPrivateMb) MB" }
    $tradeStationHealthy = $operational.TradeStationAlive -and $operational.TradeStationResponding
    Write-StatusLine "TradeStation ORPlat" "$($operational.TradeStationAlive) (responding=$($operational.TradeStationResponding))" $(if ($tradeStationHealthy) { "Healthy" } else { "Failed" })
    Write-StatusLine "TradeStation private RAM" $tradeStationRam $(if ($null -eq $operational.TradeStationPrivateMb) { "Missing" } else { "Neutral" })
    Write-StatusLine "Docker Desktop process" "$($operational.DockerDesktopAlive)" $(if ($operational.DockerDesktopAlive) { "Healthy" } else { "Failed" })
    Write-StatusLine "Docker backend process" "$($operational.DockerBackendAlive)" $(if ($operational.DockerBackendAlive) { "Healthy" } else { "Failed" })
    Write-StatusLine "Docker engine" "$($operational.DockerEngineReady)" $(if ($operational.DockerEngineReady) { "Healthy" } else { "Failed" })
    Write-StatusLine "Redis container" "$($operational.RedisContainerStatus)" $(if ($operational.RedisContainerStatus -eq "running") { "Healthy" } elseif ($operational.RedisContainerStatus -in @("missing", "unavailable")) { "Missing" } else { "Failed" })
    Write-StatusLine "Redis PING" "$($operational.RedisPing)" $(if ($operational.RedisPing) { "Healthy" } else { "Failed" })
    Write-StatusLine "System available RAM" $availableRam $(if ($null -eq $operational.SystemAvailableRamMb) { "Missing" } else { "Neutral" })
    Write-StatusLine "Bar ingestion mode" "$($operational.IngestMode)" $(if ($operational.IngestMode -eq "live") { "Healthy" } elseif ($operational.IngestMode -eq "unknown") { "Missing" } else { "Failed" })
    Write-StatusLine "Last validated bar" $barAge $(if ($null -eq $operational.LastValidatedBarAgeSeconds) { "Missing" } elseif ($operational.LastValidatedBarAgeSeconds -le 90) { "Healthy" } else { "Failed" })
    Write-StatusLine "Last transformer feature" $featureAge $(if ($null -eq $operational.LastTransformerFeatureAgeSeconds) { "Missing" } elseif ($operational.LastTransformerFeatureAgeSeconds -le 90) { "Healthy" } else { "Failed" })
    Write-StatusLine "Router ready" "$($operational.RouterReady)" $(if ($operational.RouterReady) { "Healthy" } else { "Failed" })
    Write-StatusLine "Seven-day test observer" "$($operational.LiveTestObserverActive)" $(if ($operational.LiveTestObserverActive) { "Healthy" } else { "Failed" })

    $missing = @($Rows | Where-Object { $_.Status -eq "MISSING" })
    $freshBar = $null -ne $operational.LastValidatedBarAgeSeconds -and $operational.LastValidatedBarAgeSeconds -le 90
    $freshFeature = $null -ne $operational.LastTransformerFeatureAgeSeconds -and $operational.LastTransformerFeatureAgeSeconds -le 90
    $safe = (
        $missing.Count -eq 0 -and
        $operational.TradeStationAlive -and
        $operational.TradeStationResponding -and
        $operational.DockerEngineReady -and
        $operational.RedisContainerStatus -eq "running" -and
        $operational.RedisPing -and
        $operational.RouterReady -and
        $operational.IngestMode -eq "live" -and
        $freshBar -and
        $freshFeature
    )
    if ($safe) {
        Write-Host "`nEXECUTION READINESS: SAFE" -ForegroundColor Green
        Write-Host "This indicates a healthy live pipeline; it does not assert that a position is open." -ForegroundColor DarkGray
        return $true
    }

    Write-Host "`nEXECUTION READINESS: BLOCKED" -ForegroundColor Red
    if ($missing.Count -gt 0) {
        Write-Host "Missing port(s): $($missing.Port -join ', ')" -ForegroundColor Yellow
    }
    Write-Host "Do not rely on automated decisions until every condition above is healthy and mode is live." -ForegroundColor Yellow
    return $false
}

if ($Watch) {
    try {
        $host.UI.RawUI.WindowTitle = "GNET Operational Dashboard"
    } catch {
        # Some non-interactive hosts do not expose a writable window title.
    }
    while ($true) {
        try {
            Clear-Host
        } catch {
            # Non-interactive hosts may not expose a screen buffer to clear.
        }
        [void](Show-GnetPortStatus -Rows @(Get-GnetPortStatus))
        Write-Host "`nRefreshing every $IntervalSeconds second(s). Press Ctrl+C to stop." -ForegroundColor DarkGray
        Start-Sleep -Seconds $IntervalSeconds
    }
}

$ready = Show-GnetPortStatus -Rows @(Get-GnetPortStatus)
if ($ready) {
    exit 0
}

Write-Host "Start or restart the pipeline with: .\restart.ps1" -ForegroundColor Yellow
exit 1

[CmdletBinding()]
param(
    [ValidateRange(10, 86400)]
    [int]$IntervalSeconds = 600,

    [string]$OutputDirectory = (Join-Path $PSScriptRoot "memory_logs"),

    [switch]$Once
)

$ErrorActionPreference = "Stop"

$gnetTsProcessNames = @(
    "ORPlat",
    "orchart",
    "ORCAL",
    "ORCLPrxy",
    "ORDllHst",
    "WHServer",
    "TSDev",
    "TradeStationAgentForms",
    "TSLoggerService",
    "TsRTAServer",
    "TSScanner"
)

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$gnetMemoryLog = Join-Path $OutputDirectory (
    "tradestation_memory_{0}.csv" -f (Get-Date -Format "yyyyMMdd_HHmmss")
)

function Get-GnetMemorySnapshot {
    $gnetProcesses = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $gnetTsProcessNames -contains $_.ProcessName }

    $gnetCounters = Get-Counter `
        "\Memory\Available MBytes", `
        "\Memory\% Committed Bytes In Use"

    $gnetAvailableMb = ($gnetCounters.CounterSamples |
        Where-Object Path -Like "*available mbytes").CookedValue
    $gnetCommittedPercent = ($gnetCounters.CounterSamples |
        Where-Object Path -Like "*% committed bytes in use").CookedValue

    $gnetOrPlat = $gnetProcesses |
        Where-Object ProcessName -EQ "ORPlat" |
        Select-Object -First 1
    $gnetOrChart = $gnetProcesses |
        Where-Object ProcessName -EQ "orchart" |
        Select-Object -First 1
    $gnetDllHost = $gnetProcesses |
        Where-Object ProcessName -EQ "ORDllHst" |
        Select-Object -First 1

    [pscustomobject]@{
        timestamp                    = (Get-Date).ToString("o")
        process_count                = $gnetProcesses.Count
        total_working_set_mb         = [math]::Round(
            ($gnetProcesses | Measure-Object WorkingSet64 -Sum).Sum / 1MB,
            1
        )
        total_private_mb             = [math]::Round(
            ($gnetProcesses | Measure-Object PrivateMemorySize64 -Sum).Sum / 1MB,
            1
        )
        orplat_working_set_mb        = if ($gnetOrPlat) {
            [math]::Round($gnetOrPlat.WorkingSet64 / 1MB, 1)
        } else { $null }
        orplat_private_mb            = if ($gnetOrPlat) {
            [math]::Round($gnetOrPlat.PrivateMemorySize64 / 1MB, 1)
        } else { $null }
        orchart_working_set_mb       = if ($gnetOrChart) {
            [math]::Round($gnetOrChart.WorkingSet64 / 1MB, 1)
        } else { $null }
        orchart_private_mb           = if ($gnetOrChart) {
            [math]::Round($gnetOrChart.PrivateMemorySize64 / 1MB, 1)
        } else { $null }
        ordllhst_working_set_mb      = if ($gnetDllHost) {
            [math]::Round($gnetDllHost.WorkingSet64 / 1MB, 1)
        } else { $null }
        ordllhst_private_mb          = if ($gnetDllHost) {
            [math]::Round($gnetDllHost.PrivateMemorySize64 / 1MB, 1)
        } else { $null }
        system_available_ram_mb      = [math]::Round($gnetAvailableMb, 1)
        system_committed_percent     = [math]::Round($gnetCommittedPercent, 1)
        all_processes_responding     = -not ($gnetProcesses |
            Where-Object { -not $_.Responding })
    }
}

$gnetFirstSnapshot = $null

Write-Host "=== TradeStation Memory Monitor ==="
Write-Host "Read-only sampling interval: $IntervalSeconds seconds"
Write-Host "CSV log: $gnetMemoryLog"
Write-Host "Press Ctrl+C to stop."

do {
    try {
        $gnetSnapshot = Get-GnetMemorySnapshot

        if (-not $gnetFirstSnapshot) {
            $gnetFirstSnapshot = $gnetSnapshot
        }

        $gnetSnapshot | Export-Csv `
            -LiteralPath $gnetMemoryLog `
            -Append `
            -NoTypeInformation

        $gnetPrivateGrowth = [math]::Round(
            $gnetSnapshot.total_private_mb - $gnetFirstSnapshot.total_private_mb,
            1
        )

        Write-Host ""
        $gnetDisplayFormat = (
            "[{0}] TS private={1} MB ({2:+0.0;-0.0;0.0} MB) | " +
            "ORPlat={3} MB | orchart={4} MB | DLL host={5} MB | " +
            "available RAM={6} MB | responding={7}"
        )
        Write-Host ($gnetDisplayFormat -f `
            $gnetSnapshot.timestamp,
            $gnetSnapshot.total_private_mb,
            $gnetPrivateGrowth,
            $gnetSnapshot.orplat_private_mb,
            $gnetSnapshot.orchart_private_mb,
            $gnetSnapshot.ordllhst_private_mb,
            $gnetSnapshot.system_available_ram_mb,
            $gnetSnapshot.all_processes_responding)
    }
    catch {
        Write-Warning ("Memory sample failed at {0}: {1}" -f `
            (Get-Date).ToString("o"), $_.Exception.Message)
    }

    if (-not $Once) {
        Start-Sleep -Seconds $IntervalSeconds
    }
} while (-not $Once)

[CmdletBinding()]
param(
    [switch]$AutomatedOnly,
    [switch]$SkipServiceChecks,
    [switch]$IncludeTrainingDependencies,
    [switch]$PreTraining,
    [string]$ExpectedInstallRoot = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$installRoot = if ($ExpectedInstallRoot) {
    [System.IO.Path]::GetFullPath($ExpectedInstallRoot).TrimEnd("\")
} else {
    $root.TrimEnd("\")
}
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Pass([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Add-Failure([string]$Message) {
    $script:failures.Add($Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Test-RequiredFile([string]$RelativePath) {
    $path = Join-Path $root $RelativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Add-Pass $RelativePath
    } else {
        Add-Failure "Missing required file: $RelativePath"
    }
}

function Get-PeMachine([string]$Path) {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64) { return 0 }
    $peOffset = [BitConverter]::ToInt32($bytes, 0x3c)
    if ($peOffset -lt 0 -or $peOffset + 6 -gt $bytes.Length) { return 0 }
    return [BitConverter]::ToUInt16($bytes, $peOffset + 4)
}

Write-Host "=== GNET MA-13 installation verification ===" -ForegroundColor Cyan
Write-Host "Installation root: $root"

$requiredFiles = @(
    "requirements-runtime-lock.txt",
    "config\setting.py",
    "feat_files\canonical_features.py",
    "feat_files\transformer_features.py",
    "inference\strategy_router.py",
    "inference\candidate_tcp_server.py",
    "inference\signal_tcp_server.py",
    "EL_files\BarBridge.dll",
    "EL_files\TickBridge.dll",
    "EL_files\StrategyBridge.dll",
    "EL_files\SignalBridge.dll",
    "EL_files\g_cpp_dll_bar.els",
    "EL_files\g_cpp_dll_tick.els",
    "EL_files\G_MA_CROSS_NN.els"
)
if ($PreTraining) {
    $requiredFiles += "model_registry\MA2CrossLE\registry.template.json"
} else {
    $requiredFiles += @(
        "model_registry\MA2CrossLE\registry.json",
        "training_mlp\strategies\MA2CrossLE\model\mlp_baseline\model_best.pt",
        "training_mlp\strategies\MA2CrossLE\model\mlp_baseline\scaler_best.pkl",
        "training_mlp\strategies\MA2CrossLE\model\mlp_baseline\config.json"
    )
}
$requiredFiles | ForEach-Object { Test-RequiredFile $_ }

foreach ($dll in @("BarBridge.dll", "TickBridge.dll", "StrategyBridge.dll", "SignalBridge.dll")) {
    $dllPath = Join-Path $root "EL_files\$dll"
    if (Test-Path -LiteralPath $dllPath -PathType Leaf) {
        if ((Get-PeMachine $dllPath) -eq 0x014c) {
            Add-Pass "$dll is an x86 PE binary"
        } else {
            Add-Failure "$dll is not a valid x86 PE binary"
        }
    }
}

$expectedDllRoot = Join-Path $installRoot "EL_files"
foreach ($elFile in @("g_cpp_dll_bar.els", "g_cpp_dll_tick.els", "G_MA_CROSS_NN.els")) {
    $elPath = Join-Path $root "EL_files\$elFile"
    if (Test-Path -LiteralPath $elPath) {
        $content = Get-Content -LiteralPath $elPath -Raw
        if ($content.Contains($expectedDllRoot)) {
            Add-Pass "$elFile uses this installation's DLL directory"
        } else {
            Add-Failure "$elFile does not reference $expectedDllRoot"
        }
    }
}

$strategyPath = Join-Path $root "EL_files\G_MA_CROSS_NN.els"
if (Test-Path -LiteralPath $strategyPath) {
    $strategyContent = Get-Content -LiteralPath $strategyPath -Raw
    if ($strategyContent -match "EntryPrice\s*[+-]\s*(ProfitTargetPoints|StopLossPoints)") {
        Add-Failure "G_MA_CROSS_NN still contains obsolete explicit next-bar protective exits"
    } else {
        Add-Pass "G_MA_CROSS_NN delegates protection to built-in TradeStation components"
    }
}

try {
    $pythonExe = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw "The packaged GNET Python runtime is unavailable at $pythonExe. Run .\install.ps1 first."
    }
    $runtimeArguments = @((Join-Path $root "automation\verify_runtime.py"), "--root", $root)
    if ($IncludeTrainingDependencies) { $runtimeArguments += "--include-training" }
    if ($PreTraining) { $runtimeArguments += "--pre-training" }
    $pythonOutput = & $pythonExe @runtimeArguments 2>&1
    $pythonOutput | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Add-Failure "Pinned Python/model runtime verification failed"
    }
} catch {
    Add-Failure "Could not verify Python 3.12.7: $($_.Exception.Message)"
}

if (-not $SkipServiceChecks) {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Add-Failure "Docker Desktop engine is unavailable"
    } else {
        Add-Pass "Docker Desktop engine is available"
        $redisRunning = (& docker inspect -f "{{.State.Running}}" redis1 2>$null).Trim()
        if ($LASTEXITCODE -eq 0 -and $redisRunning -eq "true") {
            Add-Pass "Redis container redis1 is running"
            $pong = (& docker exec redis1 redis-cli PING 2>$null).Trim()
            if ($LASTEXITCODE -eq 0 -and $pong -eq "PONG") {
                Add-Pass "Redis responds to PING"
            } else {
                Add-Failure "Redis did not answer PONG"
            }
            $ready = (& docker exec redis1 redis-cli GET gnet:strategy_router:ready 2>$null).Trim()
            if ($LASTEXITCODE -eq 0 -and $ready -eq "1") {
                Add-Pass "Strategy router readiness key is set"
            } else {
                Add-Failure "Strategy router readiness key is missing"
            }
        } else {
            Add-Failure "Redis container redis1 is not running"
        }
    }

    foreach ($port in @(9009, 9010, 9011, 9012, 9020)) {
        $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($listener) {
            Add-Pass "TCP port $port is listening"
        } else {
            Add-Failure "TCP port $port is not listening"
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "AUTOMATED VERIFICATION FAILED ($($failures.Count) issue(s))." -ForegroundColor Red
    Write-Host "Manual acceptance cannot be recorded until every automatic check passes."
    exit 1
}

Write-Host ""
Write-Host "AUTOMATED VERIFICATION PASSED." -ForegroundColor Green
if ($AutomatedOnly) { exit 0 }

if ($PreTraining) {
    Write-Host ""
    Write-Host "PRE-TRAINING INSTALLATION PASSED." -ForegroundColor Green
    Write-Host "Train and validate MA2CrossLE locally, activate registry.json, then rerun this verifier without -PreTraining before TradeStation acceptance."
    exit 0
}

Write-Host ""
Write-Host "Complete these checks in TradeStation simulation:" -ForegroundColor Yellow
Write-Host "  [ ] g_cpp_dll_bar is applied once to the correct 30-second symbol chart."
Write-Host "  [ ] g_cpp_dll_tick is applied once to the correct 1-tick symbol chart."
Write-Host "  [ ] G_MA_CROSS_NN uses StrategyId MA2CrossLE and a unique InstanceId."
Write-Host "  [ ] TradeStation's built-in Stop Loss is $50 per contract."
Write-Host "  [ ] TradeStation's built-in Profit Target is $50 per contract."
Write-Host "  [ ] Position size is one contract and pyramiding is disabled."
Write-Host "  [ ] An approved simulated candidate places exactly one entry."
Write-Host "  [ ] The stop and target protect the same entry bar correctly."
Write-Host "  [ ] The intended simulation account is selected; live automation is disabled."
Write-Host ""
$confirmation = Read-Host "After personally checking every item, type YES to record acceptance"
if ($confirmation -cne "YES") {
    Write-Host "Manual acceptance was not confirmed." -ForegroundColor Yellow
    exit 2
}

$acceptanceDirectory = Join-Path $root "acceptance"
New-Item -ItemType Directory -Path $acceptanceDirectory -Force | Out-Null
$record = [ordered]@{
    product = "GNET MA-13"
    accepted_at = (Get-Date).ToString("o")
    windows_user = [Environment]::UserName
    computer = [Environment]::MachineName
    installation_root = $root
    automatic_checks = "passed"
    manual_tradestation_simulation_checks = "confirmed_by_user"
}
$recordPath = Join-Path $acceptanceDirectory ("acceptance_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".json")
$record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
Write-Host "Acceptance recorded: $recordPath" -ForegroundColor Green

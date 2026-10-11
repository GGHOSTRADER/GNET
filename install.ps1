[CmdletBinding()]
param(
    [switch]$RuntimeOnly,
    [switch]$AllowNonstandardPath,
    [switch]$SkipRedisSetup,
    [string]$RedisImage = "redis:7.4.2-alpine"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path.TrimEnd("\")
$standardRoot = "C:\GNET"

Write-Host "=== GNET customer installation ===" -ForegroundColor Cyan
Write-Host "Source directory: $projectRoot"
Write-Host "Manual prerequisites: 64-bit Windows, Python.org CPython 3.12.7, Docker Desktop, TradeStation Desktop, ES market-data access, and permission to import EasyLanguage documents."

if (-not $AllowNonstandardPath -and $projectRoot -ne $standardRoot) {
    throw @"
GNET must be installed at C:\GNET because the supplied TradeStation EasyLanguage
files reference C:\GNET\EL_files. Copy this complete source directory to C:\GNET
and run C:\GNET\install.ps1 again.

For package testing only, use -AllowNonstandardPath. This does not change the
EasyLanguage DLL paths used by the delivered TradeStation configuration.
"@
}

$preTrainingPackage = Test-Path -LiteralPath (Join-Path $projectRoot "model_registry\MA2CrossLE\registry.template.json") -PathType Leaf
$requiredFiles = @(
    "requirements-runtime-lock.txt",
    "requirements-development-lock.txt",
    "verify_install.ps1",
    "automation\verify_runtime.py",
    "EL_files\BarBridge.dll",
    "EL_files\TickBridge.dll",
    "EL_files\StrategyBridge.dll",
    "EL_files\SignalBridge.dll"
)
if ($preTrainingPackage) {
    $requiredFiles += "model_registry\MA2CrossLE\registry.template.json"
} else {
    $requiredFiles += @(
        "model_registry\MA2CrossLE\registry.json",
        "training_mlp\strategies\MA2CrossLE\model\mlp_baseline\model_best.pt",
        "training_mlp\strategies\MA2CrossLE\model\mlp_baseline\scaler_best.pkl",
        "training_mlp\strategies\MA2CrossLE\model\mlp_baseline\config.json"
    )
}
foreach ($relativePath in $requiredFiles) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Installation package is incomplete; missing $relativePath"
    }
}
$packageDescription = if ($preTrainingPackage) { "source, local-training template, and DLL" } else { "source, model, and DLL" }
Write-Host "[PASS] Required $packageDescription files are present" -ForegroundColor Green

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    throw "The Windows Python launcher (py.exe) was not found. Install 64-bit CPython 3.12.7 from Python.org and retry."
}
$pythonIdentityJson = (& $pythonLauncher.Source -3.12 -c "import json,platform,sys; print(json.dumps({'version': platform.python_version(), 'implementation': platform.python_implementation(), 'executable': sys.executable}))").Trim()
if ($LASTEXITCODE -ne 0) {
    throw "The Windows Python launcher could not start CPython 3.12.7. Install that exact 64-bit Python.org release and retry."
}
$pythonIdentity = $pythonIdentityJson | ConvertFrom-Json
if ($pythonIdentity.version -ne "3.12.7" -or $pythonIdentity.implementation -ne "CPython") {
    throw "GNET requires CPython 3.12.7; py -3.12 reported $($pythonIdentity.implementation) $($pythonIdentity.version)"
}
if ($pythonIdentity.executable -match "(?i)(anaconda|conda|miniconda)") {
    throw "The selected Python belongs to Conda ($($pythonIdentity.executable)). Install CPython 3.12.7 from Python.org so GNET can create an independent runtime."
}
Write-Host "[PASS] Python.org CPython 3.12.7 bootstrap: $($pythonIdentity.executable)" -ForegroundColor Green

$venvRoot = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Write-Host "Creating isolated environment at $venvRoot ..."
    & $pythonLauncher.Source -3.12 -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "Python virtual-environment creation failed" }
} else {
    Write-Host "Using existing virtual environment at $venvRoot"
}

$requirementsFile = if ($RuntimeOnly) {
    Join-Path $projectRoot "requirements-runtime-lock.txt"
} else {
    Join-Path $projectRoot "requirements-development-lock.txt"
}
$installationKind = if ($RuntimeOnly) { "live runtime" } else { "live and training" }
Write-Host "Installing pinned $installationKind dependencies ..."
& $venvPython -m pip install --disable-pip-version-check -r $requirementsFile
if ($LASTEXITCODE -ne 0) { throw "Pinned dependency installation failed" }

& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Installed Python environment has dependency conflicts" }
Write-Host "[PASS] Pinned dependencies installed without conflicts" -ForegroundColor Green

$localDirectories = @(
    ".runtime",
    "acceptance",
    "historical_vp\raw",
    "historical_vp\prepared",
    "historical_vp\features",
    "training_mlp\strategies\MA2CrossLE\inputs",
    "training_mlp\strategies\MA2CrossLE\processed",
    "training_mlp\strategies\MA2CrossLE\model\mlp_baseline",
    "training_mlp\strategies\MA2CrossLE\reports"
)
foreach ($relativeDirectory in $localDirectories) {
    New-Item -ItemType Directory -Path (Join-Path $projectRoot $relativeDirectory) -Force | Out-Null
}

$trainingEnvironmentPath = Join-Path $projectRoot "training_mlp\.env"
if (-not (Test-Path -LiteralPath $trainingEnvironmentPath)) {
    $trainingEnvironment = @(
        "# Generated locally by install.ps1. This file is not part of the delivered source package.",
        "STRATEGY_NAME=MA2CrossLE",
        "SIGNAL_NAME=MA2CrossLE",
        "MODEL_NAME=mlp_baseline",
        "INPUTS_DIR=strategies/MA2CrossLE/inputs",
        "PROCESSED_DIR=strategies/MA2CrossLE/processed",
        "MODEL_DIR=strategies/MA2CrossLE/model/mlp_baseline",
        "REPORTS_DIR=strategies/MA2CrossLE/reports",
        "TRADES_FILE=trades_30.csv",
        "BARS_FILE=data_30.txt"
    )
    [System.IO.File]::WriteAllLines(
        $trainingEnvironmentPath,
        $trainingEnvironment,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "[PASS] Created local non-secret training_mlp\.env" -ForegroundColor Green
} else {
    Write-Host "[PASS] Preserved existing local training_mlp\.env" -ForegroundColor Green
}
Write-Host "[PASS] Runtime, acceptance, historical-data, and strategy directories are ready" -ForegroundColor Green

$previousPath = $env:Path
try {
    $env:Path = (Join-Path $venvRoot "Scripts") + ";" + $env:Path
    $verifyArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $projectRoot "verify_install.ps1"),
        "-AutomatedOnly",
        "-SkipServiceChecks",
        "-ExpectedInstallRoot", $standardRoot
    )
    if (-not $RuntimeOnly) { $verifyArguments += "-IncludeTrainingDependencies" }
    if ($preTrainingPackage) { $verifyArguments += "-PreTraining" }
    & powershell @verifyArguments
    if ($LASTEXITCODE -ne 0) { throw "GNET automatic installation verification failed" }
} finally {
    $env:Path = $previousPath
}

if (-not $SkipRedisSetup) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw "Docker Desktop is not installed or the docker command is not on PATH. Install and start Docker Desktop, then rerun install.ps1."
    }

    & $docker.Source info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is installed, but its engine is not running. Start Docker Desktop and rerun install.ps1."
    }
    Write-Host "[PASS] Docker Desktop engine is running" -ForegroundColor Green

    $existingContainerId = (& $docker.Source container ls -a --filter "name=^/redis1$" --format "{{.ID}}").Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not inspect Docker containers" }

    if ($existingContainerId) {
        $containerJson = & $docker.Source inspect redis1
        if ($LASTEXITCODE -ne 0) { throw "Could not inspect existing redis1 container" }
        $container = ($containerJson | ConvertFrom-Json)[0]
        $bindings = $container.HostConfig.PortBindings.'6379/tcp'
        $correctBinding = $bindings -and
            $bindings.Count -eq 1 -and
            $bindings[0].HostIp -eq "127.0.0.1" -and
            $bindings[0].HostPort -eq "6381"
        $persistentMount = $container.Mounts | Where-Object {
            $_.Destination -eq "/data" -and $_.Type -eq "volume"
        }
        if (-not $correctBinding -or -not $persistentMount) {
            throw @"
An existing Docker container named redis1 has a different configuration.
The installer will not delete or replace it because it may contain data.
Expected: 127.0.0.1:6381 -> 6379/tcp and a Docker volume mounted at /data.
Back up and remove the conflicting container manually before retrying.
"@
        }
        Write-Host "[PASS] Existing redis1 configuration is compatible" -ForegroundColor Green
    } else {
        Write-Host "Downloading pinned Redis image $RedisImage ..."
        & $docker.Source pull $RedisImage
        if ($LASTEXITCODE -ne 0) { throw "Could not download Redis image $RedisImage" }

        & $docker.Source volume inspect gnet-redis-data *> $null
        if ($LASTEXITCODE -ne 0) {
            & $docker.Source volume create gnet-redis-data | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not create Docker volume gnet-redis-data" }
        }

        Write-Host "Creating persistent redis1 container ..."
        & $docker.Source run `
            --name redis1 `
            --restart unless-stopped `
            --publish "127.0.0.1:6381:6379" `
            --mount "source=gnet-redis-data,target=/data" `
            --detach `
            $RedisImage `
            redis-server --appendonly yes --appendfsync everysec | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not create redis1 container" }
    }

    $running = (& $docker.Source inspect --format "{{.State.Running}}" redis1).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not read redis1 state" }
    if ($running -ne "true") {
        & $docker.Source start redis1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not start redis1" }
    }

    $redisReady = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        $pong = (& $docker.Source exec redis1 redis-cli PING 2>$null).Trim()
        if ($LASTEXITCODE -eq 0 -and $pong -eq "PONG") {
            $redisReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $redisReady) { throw "redis1 did not answer PONG within 30 seconds" }
    Write-Host "[PASS] Persistent Redis is running at 127.0.0.1:6381 and answered PONG" -ForegroundColor Green
} else {
    Write-Warning "Redis setup was skipped by request"
}

Write-Host ""
Write-Host "GNET Python installation completed successfully." -ForegroundColor Green
Write-Host "Next steps:"
if ($preTrainingPackage) {
    Write-Host "  1. Add properly licensed local bars and trade labels under the MA2CrossLE input directory."
    Write-Host "  2. Follow documentation\\guides\\TRAINING_GUIDE.md to build and validate model_best.pt, scaler_best.pkl, and config.json."
    Write-Host "  3. Copy registry.template.json to registry.json, verify its paths, and enable it only after model validation."
    Write-Host "  4. Run .\verify_install.ps1 and then complete the TradeStation simulation checklist."
} else {
    Write-Host "  1. Import the three supplied EasyLanguage documents into TradeStation."
    Write-Host "  2. Apply the built-in Stop Loss and Profit Target at `$50 per contract."
    Write-Host "  3. Launch GNET with .\launch_grid.ps1."
    Write-Host "  4. Run .\verify_install.ps1 and complete its TradeStation simulation checklist."
}
if ($RuntimeOnly) {
    Write-Host ""
    Write-Host "Training tools were not installed. Rerun install.ps1 without -RuntimeOnly when required."
}

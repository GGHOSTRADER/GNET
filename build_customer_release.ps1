[CmdletBinding()]
param(
    [string]$Destination = ".\.artifacts\customer_release\GNET_Zona-customer-source",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path $PSScriptRoot).Path
$destinationPath = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot $Destination))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $sourceRoot ".artifacts\customer_release"))

if (-not $destinationPath.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must remain under $allowedRoot"
}
if (Test-Path -LiteralPath $destinationPath) {
    if (-not $Force) {
        throw "Release destination already exists. Inspect it or rerun with -Force."
    }
    Remove-Item -LiteralPath $destinationPath -Recurse -Force
}

$excludedDirectoryNames = @(
    ".git", ".artifacts", ".claude", ".codex", ".obsidian", ".pytest_cache",
    ".runtime", ".test_artifacts", "__pycache__", "acceptance", "wandb",
    "build_hardened", "deliverables", "tmp"
)
$excludedRootFiles = @(
    "AGENTS.md", "CLAUDE.md", "build_customer_release.ps1"
)
$excludedExtensions = @(".pyc", ".pyo", ".obj", ".exp", ".lib")
$requiredDlls = @("BarBridge.dll", "TickBridge.dll", "SignalBridge.dll", "StrategyBridge.dll")
function Get-ReleaseRelativePath([string]$root, [string]$path) {
    $rootWithSeparator = $root.TrimEnd("\") + "\"
    if (-not $path.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside release root: $path"
    }
    return $path.Substring($rootWithSeparator.Length)
}

function Test-IsGeneratedTrainingData([string]$relativePath) {
    $normalized = $relativePath.Replace("\", "/")
    if ($normalized -match "^historical_vp/(raw|prepared|features)/") { return $true }
    if ($normalized -match "^training_mlp/(charts|experiments)/") { return $true }
    if ($normalized -match "^training_mlp/(df_enriched|df_features_labeled|trades_30)\.(csv|xlsx|parquet)$") { return $true }
    if ($normalized -eq "training_mlp/data_30.txt") { return $true }
    if ($normalized -match "^training_mlp/strategies/.+/(inputs|processed|reports|model)/") { return $true }
    return $false
}

New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null

$sourceFiles = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object {
    $relative = Get-ReleaseRelativePath $sourceRoot $_.FullName
    $segments = $relative -split "[\\/]"
    if ($segments | Where-Object { $_ -in $excludedDirectoryNames -or $_ -like ".tmp_*" }) { return $false }
    if ($segments.Count -eq 1 -and $_.Name -in $excludedRootFiles) { return $false }
    if ($relative.Replace("\", "/") -eq "documentation/customer_source_sale_draft.md") { return $false }
    if ($relative.Replace("\", "/") -eq "documentation/legal/SOURCE_CODE_LICENSE_AGREEMENT_DRAFT_ES.md") { return $false }
    if ($relative.Replace("\", "/") -match "^documentation/(internal|reports)/") { return $false }
    if ($_.Name -like ".env*") { return $false }
    if ($relative.Replace("\", "/") -match "^training_mlp/(zona_|_inspect_).+\.py$") { return $false }
    if ($_.Extension.ToLowerInvariant() -in $excludedExtensions) { return $false }
    if ($_.Name -match "^volumeprof\d*\.(txt|csv)$") { return $false }
    if (Test-IsGeneratedTrainingData $relative) { return $false }
    return $true
}

foreach ($file in $sourceFiles) {
    $relative = Get-ReleaseRelativePath $sourceRoot $file.FullName
    $target = Join-Path $destinationPath $relative
    $targetDirectory = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
}

# Compiled DLLs are intentionally ignored by Git but are required for the tested TradeStation release.
foreach ($dllName in $requiredDlls) {
    $sourceDll = Join-Path $sourceRoot "EL_files\$dllName"
    if (-not (Test-Path -LiteralPath $sourceDll)) { throw "Required DLL is missing: $sourceDll" }
    Copy-Item -LiteralPath $sourceDll -Destination (Join-Path $destinationPath "EL_files\$dllName") -Force
}

# Give the exported strategy/model implementation its customer-specific identity.
$releaseStrategyDirectory = Join-Path $destinationPath "training_mlp\strategies\MA2CrossLE"
$zonaStrategyDirectory = Join-Path $destinationPath "training_mlp\strategies\MA2Cross_Zona"
if (Test-Path -LiteralPath $releaseStrategyDirectory) {
    Move-Item -LiteralPath $releaseStrategyDirectory -Destination $zonaStrategyDirectory
}
$releaseRegistryDirectory = Join-Path $destinationPath "model_registry\MA2CrossLE"
$zonaRegistryDirectory = Join-Path $destinationPath "model_registry\MA2Cross_Zona"
if (Test-Path -LiteralPath $releaseRegistryDirectory) {
    Move-Item -LiteralPath $releaseRegistryDirectory -Destination $zonaRegistryDirectory
}
$activeRegistry = Join-Path $zonaRegistryDirectory "registry.json"
$registryTemplate = Join-Path $zonaRegistryDirectory "registry.template.json"
if (Test-Path -LiteralPath $activeRegistry) {
    $registry = Get-Content -LiteralPath $activeRegistry -Raw | ConvertFrom-Json
    $registry.strategy_id = "MA2Cross_Zona"
    $registry.display_name = "MA2Cross Zona"
    $registry.enabled = $false
    $registry.artifact_dir = "training_mlp/strategies/MA2Cross_Zona/model/mlp_baseline"
    $registry | Add-Member -NotePropertyName activation_note -NotePropertyValue "Copy to registry.json and enable only after local training creates and verifies model_best.pt, scaler_best.pkl, and config.json." -Force
    [System.IO.File]::WriteAllText(
        $registryTemplate,
        ($registry | ConvertTo-Json -Depth 6),
        [System.Text.UTF8Encoding]::new($false)
    )
    Remove-Item -LiteralPath $activeRegistry -Force
}
$releaseElStrategy = Join-Path $destinationPath "EL_files\G_MA_CROSS_NN.els"
$zonaElStrategy = Join-Path $destinationPath "EL_files\MA2Cross_Zona.els"
if (Test-Path -LiteralPath $releaseElStrategy) {
    Move-Item -LiteralPath $releaseElStrategy -Destination $zonaElStrategy
}

# Rewrite personal development paths only inside portable text files in the exported copy.
$textExtensions = @(".md", ".txt", ".csv", ".els", ".ps1", ".cmd", ".py", ".json", ".mmd")
$oldRoots = @(
    "C:\Users\g_med\python_new\GNET",
    "C:\\Users\\g_med\\python_new\\GNET",
    "C:\Users\g_med\py_scripts\ts_infra",
    "C:\\Users\\g_med\\py_scripts\\ts_infra"
)
foreach ($file in Get-ChildItem -LiteralPath $destinationPath -Recurse -File) {
    if ($file.Extension.ToLowerInvariant() -notin $textExtensions) { continue }
    $content = [System.IO.File]::ReadAllText($file.FullName)
    $updated = $content
    $updated = $updated.Replace($oldRoots[0], "C:\GNET_Zona")
    $updated = $updated.Replace($oldRoots[1], "C:\\GNET_Zona")
    $updated = $updated.Replace($oldRoots[2], "C:\GNET_Zona\EL_files")
    $updated = $updated.Replace($oldRoots[3], "C:\\GNET_Zona\\EL_files")
    $updated = $updated.Replace("G_MA_CROSS_NN", "MA2Cross_Zona")
    $updated = $updated.Replace("MA2CrossLE", "MA2Cross_Zona")
    $updated = [regex]::Replace($updated, '(?<![A-Za-z0-9_])GNET(?![A-Za-z0-9_])', 'GNET_Zona')
    if ($updated -ne $content) {
        [System.IO.File]::WriteAllText($file.FullName, $updated, [System.Text.UTF8Encoding]::new($false))
    }
}

$remainingPersonalPaths = Get-ChildItem -LiteralPath $destinationPath -Recurse -File | Where-Object {
    $_.Extension.ToLowerInvariant() -in $textExtensions -and
    [System.IO.File]::ReadAllText($_.FullName) -match "C:\\Users\\g_med"
}
if ($remainingPersonalPaths) {
    throw "Personal paths remain in release: $($remainingPersonalPaths.FullName -join ', ')"
}

$forbiddenReleaseFiles = Get-ChildItem -LiteralPath $destinationPath -Recurse -File -Force | Where-Object {
    $_.Name -like ".env*"
}
if ($forbiddenReleaseFiles) {
    throw "Environment files must not enter the release: $($forbiddenReleaseFiles.FullName -join ', ')"
}

$contentAudit = [ordered]@{
    schema_version = 1
    product = "GNET_Zona"
    strategy = "MA2Cross_Zona"
    source_files_selected = @($sourceFiles).Count
    release_policy = "Sanitized source and local-training capability without licensor datasets or trained-model artifacts"
    intentional_exclusions = @(
        "Environment and secret files",
        "Git and development-agent metadata",
        "Runtime caches and temporary test artifacts",
        "Historical VP raw/prepared data",
        "Historical and processed training datasets",
        "Reference-model weights, scalers, predictions, metrics, and generated model artifacts",
        "Generated experiment outputs and reports",
        "Customer release-builder tooling"
    )
    local_training = [ordered]@{
        strategy = "MA2Cross_Zona"
        registry_template = "model_registry/MA2Cross_Zona/registry.template.json"
        activation_requires = @("model_best.pt", "scaler_best.pkl", "config.json")
        data_supplied_by = "Licensee under its own licenses and permissions"
    }
}
$contentAuditPath = Join-Path $destinationPath "RELEASE_CONTENT_AUDIT.json"
[System.IO.File]::WriteAllText(
    $contentAuditPath,
    ($contentAudit | ConvertTo-Json -Depth 6),
    [System.Text.UTF8Encoding]::new($false)
)

$manifestPath = Join-Path $destinationPath "RELEASE_MANIFEST.sha256"
$manifestLines = Get-ChildItem -LiteralPath $destinationPath -Recurse -File | Where-Object {
    $_.FullName -ne $manifestPath
} | Sort-Object FullName | ForEach-Object {
    $relative = (Get-ReleaseRelativePath $destinationPath $_.FullName).Replace("\", "/")
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    "$hash  $relative"
}
[System.IO.File]::WriteAllLines($manifestPath, $manifestLines, [System.Text.UTF8Encoding]::new($false))

$fileCount = (Get-ChildItem -LiteralPath $destinationPath -Recurse -File).Count
$sizeBytes = (Get-ChildItem -LiteralPath $destinationPath -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "Customer source release created: $destinationPath"
Write-Host "Files: $fileCount"
Write-Host ("Size: {0:N2} MB" -f ($sizeBytes / 1MB))
Write-Host "Next: run verify_install.ps1 from inside the release directory."

[CmdletBinding()]
param([string]$PackageRoot,[switch]$UpdateSnapshots,[string]$Node,[string]$NodeModules,[string[]]$Spec)
$ErrorActionPreference='Stop'
$gnetRepo=Split-Path $PSScriptRoot -Parent
$gnetBundled=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node'
if(-not $Node){if(Test-Path (Join-Path $gnetBundled 'bin\node.exe')){$Node=Join-Path $gnetBundled 'bin\node.exe'}else{$Node=(Get-Command node).Source}}
if(-not $NodeModules){if(Test-Path (Join-Path $gnetRepo 'tests\browser\node_modules\playwright')){$NodeModules=Join-Path $gnetRepo 'tests\browser\node_modules'}else{$NodeModules=Join-Path $gnetBundled 'node_modules'}}
$gnetOldNodePath=$env:NODE_PATH;$gnetOldPackage=$env:GNET_BROWSER_PACKAGE
try{
 if(-not $Spec -or $Spec -contains 'generated-reports.spec.cjs'){
  $gnetFixturePython=Join-Path $gnetRepo '.venv\Scripts\python.exe'
  if(-not(Test-Path -LiteralPath $gnetFixturePython)){throw 'Generated report checks require the repository Python environment for the pinned broker renderers.'}
  & $gnetFixturePython -B (Join-Path $gnetRepo 'scripts\build_generated_chart_fixtures.py')
  if($LASTEXITCODE -ne 0){throw 'Fabricated generated-report preparation failed; browser checks not started.'}
 }
 $env:NODE_PATH=$NodeModules;if($PackageRoot){$env:GNET_BROWSER_PACKAGE=(Resolve-Path -LiteralPath $PackageRoot).Path}
 $gnetCli=Join-Path $NodeModules 'playwright\cli.js'
 if(-not(Test-Path $gnetCli)){throw 'Install browser dependencies: cd tests\browser; npm install; npx playwright install chromium. Set GNET_BROWSER_CHANNEL=chromium if Edge is unavailable.'}
 Push-Location (Join-Path $gnetRepo 'tests\browser')
 try{$gnetArgs=@($gnetCli,'test','--config=playwright.config.cjs');if($UpdateSnapshots){$gnetArgs+='--update-snapshots=all'};if($Spec){$gnetArgs+=$Spec};& $Node @gnetArgs;$gnetResult=$LASTEXITCODE}finally{Pop-Location}
 if($gnetResult -ne 0){throw "Browser suite failed (exit $gnetResult). Inspect .test_artifacts\browser\report\index.html and results traces."}
}finally{$env:NODE_PATH=$gnetOldNodePath;$env:GNET_BROWSER_PACKAGE=$gnetOldPackage}

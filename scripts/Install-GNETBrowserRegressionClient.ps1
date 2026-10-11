[CmdletBinding(SupportsShouldProcess=$true)]
param([switch]$Apply)
$ErrorActionPreference='Stop'
$gnetRepo=Split-Path $PSScriptRoot -Parent
$gnetPackage=Join-Path $gnetRepo '.artifacts\GNET-BrowserRegression-Client-v63-r2\gnet-client-v63-browser-regressions-r2'
$gnetInstall=Join-Path $gnetRepo '.artifacts\client-delivery-installed'
$gnetHash='abffdc1af1f473ff7faa8d2bf2d43df4d7d339c90a9ad2d451dd4fa9aba5ff2f'
$gnetManifestPath=Join-Path $gnetPackage 'client-release.json'
if((Get-FileHash -LiteralPath $gnetManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gnetHash){throw 'Candidate manifest differs from tested release'}
$gnetManifest=Get-Content -LiteralPath $gnetManifestPath -Raw | ConvertFrom-Json
foreach($gnetEntry in $gnetManifest.files.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $gnetPackage $gnetEntry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gnetEntry.Value){throw "Candidate file differs: $($gnetEntry.Name)"}
}
$gnetConfigPath=Join-Path $gnetInstall 'client-config.json'
$gnetConfig=Get-Content -LiteralPath $gnetConfigPath -Raw | ConvertFrom-Json
if($gnetConfig.broker_release_id -ne 'guarded-v42-recorded-review-fix'){throw 'This tested client requires the existing V42 broker pin'}
if(-not $Apply){[ordered]@{mode='plan';client_release_id=$gnetManifest.client_release_id;manifest_sha256=$gnetHash;broker_release_id=$gnetConfig.broker_release_id;install_root=$gnetInstall}|ConvertTo-Json;return}
if(-not $PSCmdlet.ShouldProcess($gnetInstall,'Install tested V63 browser fixes and restart the ordinary-user Command Center')){return}
& $gnetConfig.python -B -I (Join-Path $gnetConfig.package_root 'client_entry.py') --config $gnetConfigPath stop
if($LASTEXITCODE -ne 0){throw 'Client stop failed; installation not started'}
& (Join-Path $gnetRepo '.artifacts\GNET-Command-Center-v42-RecordedReviewFix-r3\automation\guarded_research\Install-GNETResearchClient.ps1') -PackagePath $gnetPackage -ManifestSha256 $gnetHash -Python $gnetConfig.python -InstallRoot $gnetInstall -BrokerReleaseId $gnetConfig.broker_release_id -Port $gnetConfig.port -Apply -Confirm:$false
& (Join-Path $gnetInstall 'Open-GNETResearch.ps1') -NoBrowser

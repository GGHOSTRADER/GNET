[CmdletBinding(SupportsShouldProcess=$true)]
param([switch]$Apply)
$ErrorActionPreference='Stop'
$gnetRepo=Split-Path $PSScriptRoot -Parent
$gnetPackage=Join-Path $gnetRepo '.artifacts\GNET-Compact-Delivery-Client-v67-r1\gnet-client-v67-compact-delivery-r1'
$gnetInstall=Join-Path $gnetRepo '.artifacts\client-delivery-installed'
$gnetHash='51aa26fd2963e68cbaf49ff00a7da64ded4dea5d2422e4821dfbec6da1b296b7'
$gnetManifestPath=Join-Path $gnetPackage 'client-release.json'
if((Get-FileHash -LiteralPath $gnetManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gnetHash){throw 'Candidate manifest differs from tested release'}
$gnetManifest=Get-Content -LiteralPath $gnetManifestPath -Raw | ConvertFrom-Json
foreach($gnetEntry in $gnetManifest.files.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $gnetPackage $gnetEntry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gnetEntry.Value){throw "Candidate file differs: $($gnetEntry.Name)"}
}
$gnetConfigPath=Join-Path $gnetInstall 'client-config.json'
$gnetConfig=Get-Content -LiteralPath $gnetConfigPath -Raw | ConvertFrom-Json
if($gnetConfig.broker_release_id -ne 'guarded-v42-recorded-review-fix'){throw 'This client requires the existing V42 broker pin'}
if(-not $Apply){[ordered]@{mode='plan';client_release_id=$gnetManifest.client_release_id;manifest_sha256=$gnetHash}|ConvertTo-Json;return}
if(-not $PSCmdlet.ShouldProcess($gnetInstall,'Install compact delivery labels and restart the ordinary-user Command Center')){return}
& $gnetConfig.python -B -I (Join-Path $gnetConfig.package_root 'client_entry.py') --config $gnetConfigPath stop
if($LASTEXITCODE -ne 0){throw 'Client stop failed; installation not started'}
& (Join-Path $gnetRepo '.artifacts\GNET-Command-Center-v42-RecordedReviewFix-r3\automation\guarded_research\Install-GNETResearchClient.ps1') -PackagePath $gnetPackage -ManifestSha256 $gnetHash -Python $gnetConfig.python -InstallRoot $gnetInstall -BrokerReleaseId $gnetConfig.broker_release_id -Port $gnetConfig.port -Apply -Confirm:$false
& (Join-Path $gnetInstall 'Open-GNETResearch.ps1') -NoBrowser

[CmdletBinding(SupportsShouldProcess=$true)]
param(
 [Parameter(Mandatory=$true)][string]$PackageRoot,
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256,
 [switch]$Apply,
 [switch]$GateOnly
)
$ErrorActionPreference='Stop'
$gnetRepo=Split-Path $PSScriptRoot -Parent
$gnetPackage=(Resolve-Path -LiteralPath $PackageRoot).Path
$gnetManifestPath=Join-Path $gnetPackage 'client-release.json'
if((Get-FileHash -LiteralPath $gnetManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestSha256){throw 'Candidate manifest differs from requested identity'}
$gnetManifest=Get-Content -LiteralPath $gnetManifestPath -Raw | ConvertFrom-Json
foreach($gnetEntry in $gnetManifest.files.PSObject.Properties){
 if((Get-FileHash -LiteralPath (Join-Path $gnetPackage $gnetEntry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gnetEntry.Value){throw "Candidate file differs: $($gnetEntry.Name)"}
}
$gnetInstall=Join-Path $gnetRepo '.artifacts\client-delivery-installed'
$gnetConfigPath=Join-Path $gnetInstall 'client-config.json'
$gnetConfig=Get-Content -LiteralPath $gnetConfigPath -Raw | ConvertFrom-Json
if($gnetConfig.broker_release_id -ne 'guarded-v43-native-browse-fix'){throw 'This acceptance installer supports the existing V43 broker only'}
if(-not $Apply -and -not $GateOnly){[ordered]@{mode='plan';client_release_id=$gnetManifest.client_release_id;manifest_sha256=$ManifestSha256;broker_release_id=$gnetConfig.broker_release_id;browser_gate='full suite, unchanged reviewed screenshots; failure stops before client shutdown';install_root=$gnetInstall;broker_changes=$false}|ConvertTo-Json;return}
if(-not $GateOnly -and -not $PSCmdlet.ShouldProcess($gnetInstall,'Test the entire candidate and install the ordinary-user client only on success')){return}
# Required release gate: no stop, install or launcher mutation precedes this call.
$gnetEvidence=Join-Path $gnetRepo ('.test_artifacts\release-gates\'+$gnetManifest.client_release_id+'-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
New-Item -ItemType Directory -Path $gnetEvidence -Force|Out-Null
$gnetGatePassed=$false
try{
 & (Join-Path $PSScriptRoot 'Test-GNETCommandCenterBrowser.ps1') -PackageRoot $gnetPackage
 $gnetGatePassed=$true
}finally{
 if(Test-Path -LiteralPath (Join-Path $gnetRepo '.test_artifacts\browser')){Copy-Item -LiteralPath (Join-Path $gnetRepo '.test_artifacts\browser') -Destination (Join-Path $gnetEvidence 'browser') -Recurse}
 [ordered]@{client_release_id=$gnetManifest.client_release_id;manifest_sha256=$ManifestSha256;browser_gate_passed=$gnetGatePassed;installed=$false}|ConvertTo-Json | Set-Content -LiteralPath (Join-Path $gnetEvidence 'browser-gate-result.json') -Encoding utf8
}
if((Get-FileHash -LiteralPath $gnetManifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestSha256){throw 'Candidate changed during browser acceptance'}
foreach($gnetEntry in $gnetManifest.files.PSObject.Properties){
 if((Get-FileHash -LiteralPath (Join-Path $gnetPackage $gnetEntry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $gnetEntry.Value){throw "Candidate changed during browser acceptance: $($gnetEntry.Name)"}
}
if($GateOnly){[ordered]@{mode='gate_only';client_release_id=$gnetManifest.client_release_id;manifest_sha256=$ManifestSha256;browser_gate_passed=$true;installed=$false;evidence=$gnetEvidence}|ConvertTo-Json | Tee-Object -FilePath (Join-Path $gnetEvidence 'gate-receipt.json');return}
$gnetOrigin="http://127.0.0.1:$($gnetConfig.port)"
$gnetHealth=Invoke-RestMethod -Uri "$gnetOrigin/api/client-health" -TimeoutSec 5
if($gnetHealth.client_release_id -ne $gnetConfig.client_release_id -or $gnetHealth.client_package_root -ne $gnetConfig.package_root){throw 'Port belongs to a different client; installation not started'}
$gnetStop=@{client_release_id=$gnetConfig.client_release_id;package_root=$gnetConfig.package_root}|ConvertTo-Json
Invoke-RestMethod -Uri "$gnetOrigin/api/client-stop" -Method Post -ContentType 'application/json' -Headers @{Origin=$gnetOrigin} -Body $gnetStop -TimeoutSec 5|Out-Null
Start-Sleep -Milliseconds 500
& (Join-Path $gnetRepo '.artifacts\GNET-Command-Center-v43-NativeBrowseFix-r1\automation\guarded_research\Install-GNETResearchClient.ps1') -PackagePath $gnetPackage -ManifestSha256 $ManifestSha256 -Python $gnetConfig.python -InstallRoot $gnetInstall -BrokerReleaseId $gnetConfig.broker_release_id -Port $gnetConfig.port -Apply -Confirm:$false
& (Join-Path $gnetInstall 'Open-GNETResearch.ps1') -NoBrowser
if($LASTEXITCODE -ne 0){throw 'Client launcher failed; inspect retained gate evidence'}
$gnetAfter=Invoke-RestMethod -Uri "$gnetOrigin/api/client-health" -TimeoutSec 5
if($gnetAfter.client_release_id -ne $gnetManifest.client_release_id -or $gnetAfter.broker_release_id -ne $gnetConfig.broker_release_id){throw 'Launched client identity does not match the accepted package'}
[ordered]@{client_release_id=$gnetAfter.client_release_id;broker_release_id=$gnetAfter.broker_release_id;manifest_sha256=$ManifestSha256;browser_gate_passed=$true;installed=$true;evidence=$gnetEvidence}|ConvertTo-Json | Tee-Object -FilePath (Join-Path $gnetEvidence 'installation-receipt.json')

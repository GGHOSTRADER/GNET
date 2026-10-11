[CmdletBinding(SupportsShouldProcess=$true)]
param([Parameter(Mandatory=$true)][string]$PackageRoot,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$UpdateManifestSha256,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$PackageManifestSha256,
    [string]$StateRoot=(Join-Path $env:LOCALAPPDATA 'GNETPreparation'),[switch]$Apply)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -ErrorAction Stop
function Get-GNETFixHash {
    param([string]$Path)
    $stream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read);$digest=[Security.Cryptography.SHA256]::Create()
    try{return [BitConverter]::ToString($digest.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}finally{$digest.Dispose();$stream.Dispose()}
}
function Test-GNETFixPath {
    param([string]$Path)
    $gnetCursor=[IO.Path]::GetFullPath($Path)
    while($gnetCursor){
        if(Test-Path -LiteralPath $gnetCursor){if((Get-Item -LiteralPath $gnetCursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked update path refused'}}
        $gnetCursor=Split-Path -Parent $gnetCursor
    }
}
function Test-GNETFixFile {
    param([string]$Path,$Info)
    Test-GNETFixPath $Path
    $item=Get-Item -LiteralPath $Path
    if($item.PSIsContainer -or $item.Length -ne $Info.bytes -or (Get-GNETFixHash $Path) -ne $Info.sha256){throw "File changed: $Path"}
}
function Test-GNETFixPacket {
    param([string]$Root,[string]$ManifestHash)
    Test-GNETFixPath $Root
    $control=Join-Path $Root 'preparation-release.json'
    if((Get-GNETFixHash $control) -ne $ManifestHash){throw 'Package manifest differs from supplied trust value'}
    $manifest=Get-Content -LiteralPath $control -Raw|ConvertFrom-Json
    if($manifest.schema_version -ne 'gnet-client-preparation-1' -or $manifest.activation_allowed -ne $false -or $manifest.broker_code_included -ne $false -or $manifest.payload_transfer -ne 'download_on_target'){throw 'Online preparation-only packet required'}
    if(@($manifest.files.PSObject.Properties).Count -gt 250){throw 'Packet file count exceeds cap'}
    $verifiedDownloads=0
    foreach($entry in $manifest.files.PSObject.Properties){
        if($entry.Name.Contains('..') -or $entry.Name.Contains(':') -or $entry.Name.Contains('\') -or [IO.Path]::IsPathRooted($entry.Name)){throw 'Unsafe packet path'}
        $target=Join-Path $Root $entry.Name
        $downloadable=$entry.Name -match '^(wheelhouse/[^/]+\.whl|prerequisites/python-3\.12\.7-amd64\.exe)$'
        if(-not (Test-Path -LiteralPath $target)){if($downloadable){continue};throw "Missing packet file: $($entry.Name)"}
        Test-GNETFixFile $target $entry.Value
        if($downloadable){$verifiedDownloads++}
    }
    return $verifiedDownloads
}
$PackageRoot=[IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
foreach($gnetRoot in @($PackageRoot,$StateRoot)){
    Test-GNETFixPath $gnetRoot
    foreach($boundary in @('C:\GNET_DataVault','C:\ProgramData\GNETBroker','C:\GNET_Exchange','C:\GNET_Results','C:\GNET_Import','C:\ProgramData\GNETPreparation')){
        if($gnetRoot -eq $boundary -or $gnetRoot.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase) -or $boundary.StartsWith($gnetRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Update stays outside protected deployment folders'}
    }
}
if($StateRoot -eq $PackageRoot -or $StateRoot.StartsWith($PackageRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Keep update backup outside package'}
$fixControl=Join-Path $PSScriptRoot 'update-release.json'
Test-GNETFixPath $fixControl
if((Get-GNETFixHash $fixControl) -ne $UpdateManifestSha256){throw 'Update manifest SHA256 mismatch'}
$update=Get-Content -LiteralPath $fixControl -Raw|ConvertFrom-Json
if($update.schema_version -ne 'gnet-preparation-update-2' -or @($update.replacements.PSObject.Properties).Count -gt 20){throw 'Unsupported update scope'}
foreach($entry in $update.files.PSObject.Properties){
    if($entry.Name.Contains('..') -or $entry.Name.Contains(':') -or $entry.Name.Contains('\') -or [IO.Path]::IsPathRooted($entry.Name)){throw 'Unsafe update path'}
    Test-GNETFixFile (Join-Path $PSScriptRoot $entry.Name) $entry.Value
}
$currentHash=Get-GNETFixHash (Join-Path $PackageRoot 'preparation-release.json')
if($currentHash -eq $update.target_manifest_sha256){
    $count=Test-GNETFixPacket $PackageRoot $currentHash
    @{update_applied=$true;already_applied=$true;verified_downloads_preserved=$count;installation_run=$false;manifest_sha256=$currentHash}|ConvertTo-Json;return
}
$count=Test-GNETFixPacket $PackageRoot $PackageManifestSha256
$current=Get-Content -LiteralPath (Join-Path $PackageRoot 'preparation-release.json') -Raw|ConvertFrom-Json
$next=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'payload\preparation-release.json') -Raw|ConvertFrom-Json
if((Get-GNETFixHash (Join-Path $PSScriptRoot 'payload\preparation-release.json')) -ne $update.target_manifest_sha256){throw 'Target manifest differs'}
# An externally trusted client revision may carry the customer's previous fixes.
# Every retained source, lock, download and notice must still match our release.
foreach($entry in $current.files.PSObject.Properties){
    if($update.replacements.PSObject.Properties[$entry.Name]){continue}
    $gnetNextInfo=$next.files.PSObject.Properties[$entry.Name].Value
    if(-not $gnetNextInfo -or $gnetNextInfo.sha256 -ne $entry.Value.sha256 -or $gnetNextInfo.bytes -ne $entry.Value.bytes){throw 'Unrelated package changes require review; preserved'}
}
foreach($entry in $next.files.PSObject.Properties){
    if(-not $current.files.PSObject.Properties[$entry.Name] -and -not $update.replacements.PSObject.Properties[$entry.Name]){throw 'Missing retained payload'}
}
$gnetAllowed=@('Install-GNETClientPreparation.ps1','Prepare-GNETClientPrerequisites.ps1','Prepare-GNETClientBoundaries.ps1','python_identity.py','THIRD_PARTY_INVENTORY.json','preparation-release.json','CHECKSUMS.txt','Start-GNETPreparation.cmd','HUMAN_GUIDE.md','HUMAN_AGENT_INSTALL_STEPS.md','AGENT_GUIDE.md','START_INSTALL_WITH_AGENT.md','README.md')
foreach($entry in $update.replacements.PSObject.Properties){
    if($entry.Name -notin $gnetAllowed -or $entry.Value.payload -ne ('payload/'+$entry.Name)){throw 'Unexpected replacement target'}
    Test-GNETFixFile (Join-Path $PSScriptRoot $entry.Value.payload) $entry.Value.after
    if($entry.Name -eq 'python_identity.py' -and -not $current.files.PSObject.Properties[$entry.Name] -and (Test-Path -LiteralPath (Join-Path $PackageRoot $entry.Name))){throw 'Unlisted identity probe preserved; review required'}
}
if(-not $Apply){@{mode='plan';files_to_update=@($update.replacements.PSObject.Properties).Count;verified_downloads_preserved=$count;windows_changes=$false;installation_run=$false;target_manifest_sha256=$update.target_manifest_sha256}|ConvertTo-Json;return}
if(-not $PSCmdlet.ShouldProcess($PackageRoot,'Apply reviewed installer update; retain downloads and installed preparation')){return}
$work=Join-Path (Join-Path $StateRoot 'updates') ($update.update_id+'-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $work 'backup') -Force|Out-Null
New-Item -ItemType Directory -Path (Join-Path $work 'staged')|Out-Null
$gnetBefore=@{}
foreach($entry in $update.replacements.PSObject.Properties){
    $target=Join-Path $PackageRoot $entry.Name
    if(Test-Path -LiteralPath $target){
        $gnetBefore[$entry.Name]=@{bytes=(Get-Item -LiteralPath $target).Length;sha256=(Get-GNETFixHash $target)}
        [IO.File]::Copy($target,(Join-Path (Join-Path $work 'backup') $entry.Name))
        Test-GNETFixFile (Join-Path (Join-Path $work 'backup') $entry.Name) $gnetBefore[$entry.Name]
    }
    [IO.File]::Copy((Join-Path $PSScriptRoot $entry.Value.payload),(Join-Path (Join-Path $work 'staged') $entry.Name))
    Test-GNETFixFile (Join-Path (Join-Path $work 'staged') $entry.Name) $entry.Value.after
}
$changed=@()
try{
    # Revalidate the original after snapshots, before replacing any reviewed file.
    $null=Test-GNETFixPacket $PackageRoot $PackageManifestSha256
    foreach($entry in $update.replacements.PSObject.Properties){
        $target=Join-Path $PackageRoot $entry.Name
        if($gnetBefore.ContainsKey($entry.Name)){Test-GNETFixFile $target $gnetBefore[$entry.Name]}
        elseif(Test-Path -LiteralPath $target){throw 'Replacement destination appeared during update'}
        $changed+=$entry.Name
        [IO.File]::Copy((Join-Path (Join-Path $work 'staged') $entry.Name),$target,$true)
    }
    $count=Test-GNETFixPacket $PackageRoot $update.target_manifest_sha256
}catch{
    foreach($name in $changed){
        if($gnetBefore.ContainsKey($name)){[IO.File]::Copy((Join-Path (Join-Path $work 'backup') $name),(Join-Path $PackageRoot $name),$true)}
        else{Remove-Item -LiteralPath (Join-Path $PackageRoot $name)}
    }
    throw
}
$receipt=@{update_applied=$true;already_applied=$false;files_updated=$changed.Count;verified_downloads_preserved=$count;backup=$work;manifest_sha256=$update.target_manifest_sha256;installation_run=$false;windows_changes=$false}
$receipt|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $work 'update-result.json') -Encoding UTF8
$receipt|ConvertTo-Json

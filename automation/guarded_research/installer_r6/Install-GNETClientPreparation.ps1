[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256,
    [string]$StateRoot=(Join-Path $env:LOCALAPPDATA 'GNETPreparation'),
    [string]$PreparedEnvironment='', [string]$ResearcherIdentity="$env:USERDOMAIN\$env:USERNAME",[switch]$Apply)
$ErrorActionPreference='Stop'
$gnetInstallPreparedEnvironment=$PreparedEnvironment;$gnetInstallApply=[bool]$Apply;$gnetInstallStateRoot=$StateRoot;$gnetInstallResearcher=$ResearcherIdentity;$gnetInstallCmdlet=$PSCmdlet
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -ErrorAction Stop
function Read-GNETReviewedScript {
    param([string]$Name,$Manifest)
    $info=$Manifest.files.PSObject.Properties[$Name].Value
    if(-not $info){throw 'Unlisted administrator helper'}
    $path=Join-Path $PSScriptRoot $Name
    $stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $hash=[Security.Cryptography.SHA256]::Create()
    try{
        if($stream.Length -ne $info.bytes -or [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant() -ne $info.sha256){throw 'Administrator helper changed'}
        $stream.Position=0;$memory=New-Object IO.MemoryStream
        try{$stream.CopyTo($memory);return ,$memory.ToArray()}finally{$memory.Dispose()}
    }finally{$hash.Dispose();$stream.Dispose()}
}
function Save-GNETReviewedScript {
    param([string]$Name,[byte[]]$Bytes,[string]$Root)
    $destination=Join-Path $Root $Name
    if(Test-Path -LiteralPath $destination){
        $expected=[Security.Cryptography.SHA256]::Create()
        try{$hash=[BitConverter]::ToString($expected.ComputeHash($Bytes)).Replace('-','').ToLowerInvariant()}finally{$expected.Dispose()}
        if((Get-GNETPreparationHash $destination) -ne $hash){throw 'Existing protected helper differs; no overwrite'}
    }else{
        $stream=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$stream.Write($Bytes,0,$Bytes.Length)}finally{$stream.Dispose()}
    }
    return $destination
}
$manifestPath=Join-Path $PSScriptRoot 'preparation-release.json'
$stream=[IO.File]::OpenRead($manifestPath);$hasher=[Security.Cryptography.SHA256]::Create()
try{$actual=[BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}finally{$hasher.Dispose();$stream.Dispose()}
if($actual -ne $ManifestSha256){throw 'Manifest SHA256 mismatch'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
# Execute only bytes verified while held with write/delete sharing denied.
$downloadBytes=Read-GNETReviewedScript 'Download-GNETPrerequisites.ps1' $manifest
. ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($downloadBytes))) -ManifestSha256 $ManifestSha256 -FunctionsOnly
$control=Get-GNETOnlineControl $PSScriptRoot $ManifestSha256
$preparationBytes=Read-GNETReviewedScript 'Prepare-GNETClientPrerequisites.ps1' $manifest
. ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($preparationBytes))) -ManifestSha256 $ManifestSha256 -FunctionsOnly
$boundaryBytes=Read-GNETReviewedScript 'Prepare-GNETClientBoundaries.ps1' $manifest
. ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($boundaryBytes))) -FunctionsOnly
$PreparedEnvironment=$gnetInstallPreparedEnvironment;$Apply=$gnetInstallApply;$StateRoot=$gnetInstallStateRoot;$ResearcherIdentity=$gnetInstallResearcher
if(-not $Apply){@{phase='online_preparation';researcher=$ResearcherIdentity;actions=@('Download and verify 22 prerequisites first','Verify/reuse Python and 21 locked libraries; install only when needed','Create missing disabled standard broker account','Prepare and verify 12 Windows folder boundaries');boundaries=@(Get-GNETClientBoundaryPlan);broker_activated=$false;tasks_registered=$false;data_migration=$false}|ConvertTo-Json -Depth 6;return}
if(-not $gnetInstallCmdlet.ShouldProcess('Python and libraries, GNETDataBroker, twelve GNET folder permission boundaries','Install client prerequisites and prepare Windows isolation boundaries')){return}
if([IntPtr]::Size -ne 8){throw 'Use 64-bit Administrator PowerShell'}
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Use Administrator PowerShell; the human must approve and enter any new password locally'}
$gnetLocalAccountsRoot=Join-Path $PSHOME 'Modules\Microsoft.PowerShell.LocalAccounts'
$gnetLocalAccountsManifest=Join-Path $gnetLocalAccountsRoot 'Microsoft.PowerShell.LocalAccounts.psd1'
if(-not (Test-Path -LiteralPath $gnetLocalAccountsManifest -PathType Leaf)){
    $gnetLocalAccountsManifest=$null
    $gnetModuleVersions=@(Get-ChildItem -LiteralPath $gnetLocalAccountsRoot -Directory -ErrorAction Stop|
        Where-Object {$_.Name -match '^\d+\.\d+(\.\d+){0,2}$'}|
        Sort-Object {[version]$_.Name} -Descending)
    foreach($gnetModuleVersion in $gnetModuleVersions){
        if($gnetModuleVersion.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked LocalAccounts module directory refused'}
        $gnetCandidate=Join-Path $gnetModuleVersion.FullName 'Microsoft.PowerShell.LocalAccounts.psd1'
        if(Test-Path -LiteralPath $gnetCandidate -PathType Leaf){$gnetLocalAccountsManifest=$gnetCandidate;break}
    }
}
if(-not $gnetLocalAccountsManifest){throw 'LocalAccounts module unavailable under trusted PSHOME; use 64-bit Windows PowerShell'}
if((Get-Item -LiteralPath $gnetLocalAccountsRoot).Attributes -band [IO.FileAttributes]::ReparsePoint -or
   (Get-Item -LiteralPath $gnetLocalAccountsManifest).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked LocalAccounts module refused'}
Import-Module -Name $gnetLocalAccountsManifest -ErrorAction Stop
if(-not [IO.Path]::IsPathRooted($StateRoot)){throw 'Explicit absolute researcher state path required'}
$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
foreach($boundary in @('C:\GNET_DataVault','C:\ProgramData\GNETBroker','C:\GNET_Exchange','C:\GNET_Results','C:\GNET_Import')){
    if($StateRoot -eq $boundary -or $StateRoot.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase) -or $boundary.StartsWith($StateRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Installation receipt must stay outside broker/data folders'}
}
Test-GNETClientBoundaryPreflight
$null=Test-GNETPreparationFiles $PSScriptRoot $ManifestSha256
$researcherSid=(New-Object Security.Principal.NTAccount($ResearcherIdentity)).Translate([Security.Principal.SecurityIdentifier]).Value
$existing=Get-LocalUser -Name 'GNETDataBroker' -ErrorAction SilentlyContinue
if($existing -and ($existing.SID.Value -eq $researcherSid -or @(Get-LocalGroupMember -SID 'S-1-5-32-544').SID.Value -contains $existing.SID.Value)){throw 'Existing broker identity is not isolated/standard; no installation performed'}
$receipt=[ordered]@{phase='preparation_only';python_and_libraries_installed=$false;boundaries_verified=0;permissions_prepared=$false;broker_activated=$false;tasks_registered=$false;data_migrated=$false;training_run=$false;isolation_certified=$false;failure=$null;current_step='protected_snapshot';dependencies_reused=$false;prepared_environment=$null}
New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
$receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $StateRoot 'online-installation-status.json') -Encoding UTF8
try{
    $parent='C:\ProgramData\GNETPreparation';Set-GNETPreparationDirectory $parent
    $protected=Join-Path $parent $manifest.package_id;Set-GNETPreparationDirectory $protected
    $helpers=Join-Path $protected 'admin-scripts';Set-GNETPreparationDirectory $helpers
    $prepPath=Save-GNETReviewedScript 'Prepare-GNETClientPrerequisites.ps1' $preparationBytes $helpers
    # The reviewed prerequisite script uses its own directory as payload root.
    # Snapshot the full declared packet without executing writable client helpers.
    foreach($entry in $manifest.files.PSObject.Properties){
        $source=Join-Path $PSScriptRoot $entry.Name;$destination=Join-Path $helpers $entry.Name
        if(Test-Path -LiteralPath $destination){if((Get-GNETPreparationHash $destination) -ne $entry.Value.sha256){throw 'Protected payload differs'};continue}
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force|Out-Null
        $snapshotInput=[IO.File]::Open($source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        $digest=[Security.Cryptography.SHA256]::Create()
        try{
            if([BitConverter]::ToString($digest.ComputeHash($snapshotInput)).Replace('-','').ToLowerInvariant() -ne $entry.Value.sha256){throw 'Source changed during protected snapshot'}
            $snapshotInput.Position=0;$snapshotOutput=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try{$snapshotInput.CopyTo($snapshotOutput)}finally{$snapshotOutput.Dispose()}
        }finally{$digest.Dispose();$snapshotInput.Dispose()}
    }
    $protectedManifest=Join-Path $helpers 'preparation-release.json'
    if(Test-Path -LiteralPath $protectedManifest){if((Get-GNETPreparationHash $protectedManifest) -ne $ManifestSha256){throw 'Protected control differs'}}else{[IO.File]::Copy($manifestPath,$protectedManifest)}
    if((Get-GNETPreparationHash $protectedManifest) -ne $ManifestSha256){throw 'Control changed during snapshot'}
    $receipt.current_step='prerequisites'
    $receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $StateRoot 'online-installation-status.json') -Encoding UTF8
    & $prepPath -ManifestSha256 $ManifestSha256 -StateRoot $StateRoot -PreparedEnvironment $PreparedEnvironment -Apply -Confirm:$false
    $prerequisiteReceipt=Get-Content -LiteralPath (Join-Path $StateRoot 'admin-prerequisites.json') -Raw|ConvertFrom-Json
    $receipt.dependencies_reused=$prerequisiteReceipt.dependencies_reused;$receipt.prepared_environment=$prerequisiteReceipt.prepared_environment
    $receipt.python_and_libraries_installed=$true
    $boundaryPath=Save-GNETReviewedScript 'Prepare-GNETClientBoundaries.ps1' $boundaryBytes $helpers
    $receipt.current_step='boundaries'
    $receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $StateRoot 'online-installation-status.json') -Encoding UTF8
    $boundary=& $boundaryPath -ResearcherIdentity $ResearcherIdentity -Apply -Confirm:$false|ConvertFrom-Json
    $receipt.boundaries_verified=$boundary.boundaries_verified;$receipt.permissions_prepared=($boundary.boundaries_verified -eq 12)
    if(-not $receipt.permissions_prepared){throw 'Windows boundary verification incomplete'}
    $receipt.current_step='preparation_complete'
}catch{$receipt.failure=$_.Exception.Message}
New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
$receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $StateRoot 'online-installation-status.json') -Encoding UTF8
$receipt|ConvertTo-Json -Depth 5
if($receipt.failure){throw 'Installation preparation incomplete; see online-installation-status.json'}

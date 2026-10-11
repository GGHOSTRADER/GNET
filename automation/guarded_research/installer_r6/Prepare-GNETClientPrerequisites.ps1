[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256,
    [string]$StateRoot=(Join-Path $env:LOCALAPPDATA 'GNETPreparation'),
    [string]$PreparedEnvironment='', [switch]$Apply,[switch]$FunctionsOnly)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -ErrorAction Stop
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
function Get-GNETPreparationHash {
    param([string]$LiteralPath)
    $stream=[IO.File]::Open($LiteralPath,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $hasher=[Security.Cryptography.SHA256]::Create()
    try{return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}
    finally{$hasher.Dispose();$stream.Dispose()}
}
function Test-GNETPreparationFiles {
    param([string]$Root,[string]$ExpectedHash)
    $rootItem=Get-Item -LiteralPath $Root
    if($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked preparation root refused'}
    $control=Join-Path $Root 'preparation-release.json'
    if((Get-GNETPreparationHash -LiteralPath $control) -ne $ExpectedHash){throw 'Preparation manifest differs from externally reviewed SHA256'}
    $manifest=Get-Content -LiteralPath $control -Raw|ConvertFrom-Json
    if($manifest.schema_version -ne 'gnet-client-preparation-1' -or $manifest.activation_allowed -ne $false -or $manifest.broker_code_included -ne $false){throw 'This is not a preparation-only kit'}
    if(@($manifest.files.PSObject.Properties).Count -gt 250){throw 'Preparation payload count exceeds cap'}
    foreach($file in $manifest.files.PSObject.Properties){
        if($file.Name.Contains('..') -or $file.Name.Contains(':') -or $file.Name.Contains('\') -or [IO.Path]::IsPathRooted($file.Name)){throw 'Unsafe payload path'}
        $source=[IO.Path]::GetFullPath((Join-Path $Root $file.Name))
        if(-not $source.StartsWith($rootItem.FullName.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Payload escapes package'}
        $item=Get-Item -LiteralPath $source
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint -or $item.Length -ne $file.Value.bytes -or (Get-GNETPreparationHash -LiteralPath $source) -ne $file.Value.sha256){throw 'Preparation payload differs from reviewed manifest'}
    }
    return $manifest
}
function Ensure-GNETPreparationAccount {
    $existing=Get-LocalUser -Name 'GNETDataBroker' -ErrorAction SilentlyContinue
    if($existing){
        if(@(Get-LocalGroupMember -SID 'S-1-5-32-544').SID.Value -contains $existing.SID.Value){throw 'Existing broker has administrator membership;preserved and requires review'}
        return @{account_state='Existing standard account preserved';account_created=$false;account_enabled=[bool]$existing.Enabled;sid=$existing.SID.Value}
    }
    $password=Read-Host -Prompt 'Create the new GNETDataBroker password locally (never send it to the agent)' -AsSecureString
    try{
        if(-not $password -or $password.Length -eq 0){throw 'Password entry canceled;no account created'}
        $account=New-LocalUser -Name 'GNETDataBroker' -Password $password -Disabled -Description 'GNET preparation; activation deferred' -ErrorAction Stop
        if(@(Get-LocalGroupMember -SID 'S-1-5-32-545').SID.Value -notcontains $account.SID.Value){Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $account.SID.Value -ErrorAction Stop}
        $check=Get-LocalUser -Name 'GNETDataBroker'
        if($check.Enabled -or @(Get-LocalGroupMember -SID 'S-1-5-32-544').SID.Value -contains $check.SID.Value){throw 'Prepared account must remain disabled and standard'}
        return @{account_state='New disabled standard account prepared';account_created=$true;account_enabled=$false;sid=$check.SID.Value}
    }finally{$password=$null}
}
function Set-GNETPreparationDirectory {
    param([string]$LiteralPath)
    if(Test-Path -LiteralPath $LiteralPath){
        if((Get-Item -LiteralPath $LiteralPath).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked preparation directory refused'}
        $existingAcl=Get-Acl -LiteralPath $LiteralPath
        if($existingAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Existing preparation directory has an untrusted owner;no changes made'}
        foreach($rule in $existingAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){if($rule.AccessControlType -eq 'Allow' -and $rule.IdentityReference.Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Existing prerequisite directory is not private;review before reuse'}}
        return
    }
    New-Item -ItemType Directory -Path $LiteralPath -Force|Out-Null
    $acl=New-Object Security.AccessControl.DirectorySecurity;$acl.SetAccessRuleProtection($true,$false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    foreach($sid in @('S-1-5-18','S-1-5-32-544')){$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),'FullControl','ContainerInherit,ObjectInherit','None','Allow')))}
    Set-Acl -LiteralPath $LiteralPath -AclObject $acl
}
function Get-GNETPythonIdentity {
    param([string]$Python,[string]$Probe)
    $gnetIdentityOutput=@(& $Python -B -I $Probe)
    if($LASTEXITCODE -ne 0 -or $gnetIdentityOutput.Count -ne 1){throw 'Python identity probe failed'}
    $gnetIdentity=$gnetIdentityOutput[0]|ConvertFrom-Json
    if($gnetIdentity.version -ne '3.12.7' -or $gnetIdentity.bits -ne 64){throw 'Reviewed Python 3.12.7 x64 required; existing interpreter preserved'}
    return $gnetIdentity
}
function Test-GNETPreparedEnvironment {
    param([string]$Environment)
    $gnetEnvironment=[IO.Path]::GetFullPath($Environment).TrimEnd('\')
    $gnetPrivateRoot='C:\ProgramData\GNETPreparation'
    if(-not $gnetEnvironment.StartsWith($gnetPrivateRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or
       (Split-Path -Leaf $gnetEnvironment) -ne 'venv' -or
       (Split-Path -Parent (Split-Path -Parent $gnetEnvironment)) -ne $gnetPrivateRoot){throw 'Reuse requires a direct private preparation revision venv'}
    $gnetItems=New-Object 'Collections.Generic.Queue[string]'
    foreach($gnetAncestor in @($gnetPrivateRoot,(Split-Path -Parent $gnetEnvironment))){$gnetItems.Enqueue($gnetAncestor)}
    $gnetItems.Enqueue($gnetEnvironment)
    $gnetChecked=0
    while($gnetItems.Count){
        $gnetPath=$gnetItems.Dequeue();$gnetChecked++
        if($gnetChecked -gt 45000){throw 'Prepared environment metadata inspection exceeds cap'}
        $gnetItem=Get-Item -LiteralPath $gnetPath -Force
        if($gnetItem.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked prepared environment refused'}
        $gnetAcl=Get-Acl -LiteralPath $gnetPath
        if($gnetAcl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Prepared environment owner is untrusted'}
        foreach($gnetRule in $gnetAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
            if($gnetRule.AccessControlType -eq 'Allow' -and $gnetRule.IdentityReference.Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'Prepared environment grants access outside administrators and SYSTEM'}
        }
        if($gnetItem.PSIsContainer -and ($gnetPath -eq $gnetEnvironment -or $gnetPath.StartsWith($gnetEnvironment+'\',[StringComparison]::OrdinalIgnoreCase))){
            foreach($gnetChild in Get-ChildItem -LiteralPath $gnetPath -Force){$gnetItems.Enqueue($gnetChild.FullName)}
        }
    }
    if(-not (Test-Path -LiteralPath (Join-Path $gnetEnvironment 'Scripts\python.exe') -PathType Leaf)){throw 'Partial prepared environment requires review'}
    return $gnetChecked
}
function Initialize-GNETPreparationEnvironment {
    param([string]$BasePython,[string]$Protected,[string]$PreparedEnvironment='')
    $gnetExplicitReuse=[bool]$PreparedEnvironment
    $gnetEnvironment=Join-Path $Protected 'venv'
    if($gnetExplicitReuse){$gnetEnvironment=[IO.Path]::GetFullPath($PreparedEnvironment).TrimEnd('\')}
    $gnetEnvPython=Join-Path $gnetEnvironment 'Scripts\python.exe'
    if(Test-Path -LiteralPath $gnetEnvironment){
        $null=Test-GNETPreparedEnvironment $gnetEnvironment
        $gnetSavedPreference=$ErrorActionPreference
        try{
            $ErrorActionPreference='Continue'
            $gnetVersionReport=@(& $gnetEnvPython -B -I (Join-Path $Protected 'verify_prerequisites.py') 2>&1)
            $gnetVerificationExit=$LASTEXITCODE
        }finally{$ErrorActionPreference=$gnetSavedPreference}
        if($gnetVerificationExit -eq 0){
            $gnetSummary=$gnetVersionReport[-1]|ConvertFrom-Json
            if($gnetSummary.dependency_versions_verified -ne 21 -or $gnetSummary.import_smoke_passed -ne $true){throw 'Unexpected dependency verification output'}
            return @{environment=$gnetEnvironment;dependencies_reused=$true;dependency_versions_verified=21}
        }
        if($gnetExplicitReuse){throw 'Selected existing environment failed locked version/import verification; preserved without repair'}
    }elseif($gnetExplicitReuse){throw 'Selected prepared environment is missing; no replacement created'}
    else{
        & $BasePython -B -I -m venv $gnetEnvironment
        if($LASTEXITCODE -ne 0){throw 'Preparation environment creation failed'}
    }
    $null=Test-GNETPreparedEnvironment $gnetEnvironment
    & $gnetEnvPython -B -I -m pip install --no-index --find-links (Join-Path $Protected 'wheelhouse') --require-hashes --requirement (Join-Path $Protected 'requirements-hashed.txt')
    if($LASTEXITCODE -ne 0){throw 'Offline locked dependency installation failed'}
    $null=Test-GNETPreparedEnvironment $gnetEnvironment
    & $gnetEnvPython -B -I (Join-Path $Protected 'verify_prerequisites.py')|Out-Host
    if($LASTEXITCODE -ne 0){throw 'Prepared dependency version/import smoke check failed'}
    return @{environment=$gnetEnvironment;dependencies_reused=$false;dependency_versions_verified=21}
}
function Write-GNETPreparationCheckpoint {
    param($Receipt,[string]$StateRoot)
    New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
    $Receipt|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $StateRoot 'admin-prerequisites.json') -Encoding UTF8
}

if($FunctionsOnly){return}
$manifest=Test-GNETPreparationFiles -Root $PSScriptRoot -ExpectedHash $ManifestSha256
$plan=[ordered]@{phase='preparation_only';actions=@('Verify/install administrator-owned Python3.12.7','Prepare an offline locked dependency environment','Create disabled standard broker account if absent');deferred=@('Account activation/batch-logon','Research vault/exchange/inbox permissions','Broker code/configuration','Scheduled tasks','MCP connection','TS/data admission','Training/live trading');existing_accounts_preserved=$true;data_migration=$false}
if(-not $Apply){$plan|ConvertTo-Json -Depth 4;return}
if(-not $PSCmdlet.ShouldProcess('Python prerequisites,one private preparation cache,and an optional disabled GNETDataBroker account','Prepare client prerequisites only;no broker activation or research permissions')){return}
if([IntPtr]::Size -ne 8){throw 'Use64-bit Administrator PowerShell'}
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
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Apply requires Administrator PowerShell and local human password entry'}
if(-not [IO.Path]::IsPathRooted($StateRoot)){throw 'StateRoot must be absolute'}
$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
foreach($boundary in @('C:\GNET_DataVault','C:\ProgramData\GNETBroker','C:\GNET_Exchange','C:\GNET_Results','C:\GNET_Import')){if($StateRoot -eq $boundary -or $StateRoot.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Preparation receipt must stay outside broker/data folders'}}
$parent='C:\ProgramData\GNETPreparation';Set-GNETPreparationDirectory $parent
$protected=Join-Path $parent $manifest.package_id;Set-GNETPreparationDirectory $protected
# Snapshot only reviewed prerequisites. Never execute a helper from a writable
# customer directory as part of the Administrator prerequisite installation.
foreach($file in $manifest.files.PSObject.Properties){
    if($file.Name -notmatch '^(wheelhouse/|prerequisites/|requirements-hashed\.txt$|verify_prerequisites\.py$|python_identity\.py$)'){continue}
    $source=Join-Path $PSScriptRoot $file.Name;$destination=Join-Path $protected $file.Name
    if(Test-Path -LiteralPath $destination){if((Get-GNETPreparationHash -LiteralPath $destination) -ne $file.Value.sha256){throw 'Existing prerequisite snapshot differs;no overwrite'};continue}
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force|Out-Null
    $stream=[IO.File]::Open($source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $hasher=[Security.Cryptography.SHA256]::Create()
    try{
        if([BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() -ne $file.Value.sha256){throw 'Source changed during prerequisite snapshot'}
        $stream.Position=0;$output=[IO.File]::Open($destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$stream.CopyTo($output)}finally{$output.Dispose()}
    }finally{$hasher.Dispose();$stream.Dispose()}
}
$python='C:\Program Files\Python312\python.exe'
$receipt=[ordered]@{phase='preparation_only';python_ready=$false;dependencies_ready=$false;account_state='Pending';account_created=$false;broker_activated=$false;tasks_registered=$false;research_permissions_granted=$false;data_imported=$false;training_run=$false;isolation_certified=$false;failure=$null;current_step='python';dependencies_reused=$false;prepared_environment=$null}
Write-GNETPreparationCheckpoint $receipt $StateRoot
try{
    if(-not (Test-Path -LiteralPath $python)){
        if(Test-Path -LiteralPath 'C:\Program Files\Python312'){throw 'Existing partial/different system Python requires review;no overwrite'}
        $installer=Join-Path $protected 'prerequisites\python-3.12.7-amd64.exe'
        $signature=Get-AuthenticodeSignature -LiteralPath $installer
        if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation'){throw 'Official Python installer signature did not validate'}
        $process=Start-Process -FilePath $installer -ArgumentList @('/quiet','InstallAllUsers=1','TargetDir="C:\Program Files\Python312"','PrependPath=0','Include_launcher=0','Include_test=0','Include_doc=0','Include_pip=1') -WindowStyle Hidden -Wait -PassThru
        if($process.ExitCode -notin @(0,3010)){throw 'System Python installation failed'}
    }
    $null=Get-GNETPythonIdentity $python (Join-Path $protected 'python_identity.py')
    $receipt.python_ready=$true
    $receipt.current_step='dependencies';Write-GNETPreparationCheckpoint $receipt $StateRoot
    $environmentResult=Initialize-GNETPreparationEnvironment $python $protected $PreparedEnvironment
    $receipt.dependencies_reused=$environmentResult.dependencies_reused;$receipt.prepared_environment=$environmentResult.environment
    $receipt.dependencies_ready=$true
    $receipt.current_step='account';Write-GNETPreparationCheckpoint $receipt $StateRoot
    $account=Ensure-GNETPreparationAccount
    $receipt.account_state=$account.account_state;$receipt.account_created=$account.account_created;$receipt.account_enabled=$account.account_enabled;$receipt.account_sid=$account.sid
    $receipt.current_step='prerequisites_complete'
}catch{$receipt.failure=$_.Exception.Message}
New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
$receipt|ConvertTo-Json -Depth 4|Set-Content -LiteralPath (Join-Path $StateRoot 'admin-prerequisites.json') -Encoding UTF8
$receipt|ConvertTo-Json -Depth 4
if($receipt.failure){throw 'Preparation remains incomplete;see admin-prerequisites.json. No broker deployment was performed.'}

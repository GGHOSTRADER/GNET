[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{64}$')][string]$ManifestSha256,
    [string]$StateRoot=(Join-Path $env:LOCALAPPDATA 'GNETPreparation'),
    [string]$ResearcherIdentity="$env:USERDOMAIN\$env:USERNAME",[switch]$Save)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Management\Microsoft.PowerShell.Management.psd1') -ErrorAction Stop
function ConvertTo-GNETInstallLiteral {
    param([string]$Value)
    return "'"+$Value.Replace("'","''")+"'"
}
if((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'preparation-release.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ManifestSha256){throw 'Preparation manifest SHA256 mismatch'}
if(-not [IO.Path]::IsPathRooted($StateRoot)){throw 'StateRoot must be absolute'}
$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\')
foreach($boundary in @('C:\ProgramData\GNETBroker','C:\ProgramData\GNETPreparation','C:\GNET_DataVault','C:\GNET_Exchange','C:\GNET_Results','C:\GNET_Import')){
    if($StateRoot -eq $boundary -or $StateRoot.StartsWith($boundary+'\',[StringComparison]::OrdinalIgnoreCase) -or $boundary.StartsWith($StateRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Command instructions must stay outside protected folders'}
}
if($StateRoot -eq $PSScriptRoot -or $StateRoot.StartsWith($PSScriptRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Keep generated instructions outside verified package'}
$gnetCommand='& '+(ConvertTo-GNETInstallLiteral (Join-Path $PSScriptRoot 'Install-GNETClientPreparation.ps1'))+
    ' -ManifestSha256 '+(ConvertTo-GNETInstallLiteral $ManifestSha256)+
    ' -StateRoot '+(ConvertTo-GNETInstallLiteral $StateRoot)+
    ' -ResearcherIdentity '+(ConvertTo-GNETInstallLiteral $ResearcherIdentity)+' -Apply'
$gnetText="Open 64-bit Windows PowerShell as Administrator. Paste this command, confirm locally, and enter a new broker password only in its secure local prompt if requested.`r`n`r`n"+$gnetCommand+"`r`n`r`nThis prepares Python/libraries, a disabled standard broker account, and 12 folder boundaries. Broker activation and tasks are later work.`r`n"
if($Save){
    $gnetCursor=$StateRoot
    while($gnetCursor){
        if(Test-Path -LiteralPath $gnetCursor){if((Get-Item -LiteralPath $gnetCursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked instruction path refused'}}
        $gnetCursor=Split-Path -Parent $gnetCursor
    }
    New-Item -ItemType Directory -Path $StateRoot -Force|Out-Null
    $gnetText|Set-Content -LiteralPath (Join-Path $StateRoot 'ADMIN_INSTALL_COMMAND.txt') -Encoding UTF8
}
$gnetText

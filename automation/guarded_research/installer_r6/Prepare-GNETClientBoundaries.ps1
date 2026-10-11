[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([string]$ResearcherIdentity="$env:USERDOMAIN\$env:USERNAME",[switch]$Apply,[switch]$FunctionsOnly)
$ErrorActionPreference='Stop'
function Get-GNETClientBoundaryPlan {
    return @(
        @{path='C:\ProgramData\GNETBroker';broker='ReadAndExecute';researcher=''},
        @{path='C:\ProgramData\GNETBroker\runtime';broker='ReadAndExecute';researcher=''},
        @{path='C:\ProgramData\GNETBroker\state';broker='Modify';researcher=''},
        @{path='C:\GNET_DataVault';broker='Modify';researcher=''},
        @{path='C:\GNET_Exchange';broker='ReadAndExecute';researcher='ReadAndExecute'},
        @{path='C:\GNET_Exchange\requests';broker='Modify';researcher='Modify'},
        @{path='C:\GNET_Exchange\requests\pending';broker='Modify';researcher='Modify'},
        @{path='C:\GNET_Exchange\requests\cancel';broker='Modify';researcher='Modify'},
        @{path='C:\GNET_Exchange\status';broker='Modify';researcher='ReadAndExecute'},
        @{path='C:\GNET_Results';broker='Modify';researcher='ReadAndExecute'},
        @{path='C:\GNET_Import';broker='ReadAndExecute';researcher='ReadAndExecute'},
        @{path='C:\GNET_Import\incoming';broker='Modify';researcher='producer'}
    )
}
function New-GNETClientBoundaryAcl {
    param($Definition,[string]$BrokerSid,[string]$ResearcherSid)
    if($BrokerSid -eq $ResearcherSid){throw 'Broker and researcher identities must differ'}
    $acl=New-Object Security.AccessControl.DirectorySecurity;$acl.SetAccessRuleProtection($true,$false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    foreach($sid in @('S-1-5-18','S-1-5-32-544')){$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),'FullControl','ContainerInherit,ObjectInherit','None','Allow')))}
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($BrokerSid)),$Definition.broker,'ContainerInherit,ObjectInherit','None','Allow')))
    if($Definition.researcher -eq 'producer'){
        $identity=New-Object Security.Principal.SecurityIdentifier($ResearcherSid)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'ReadAndExecute,CreateDirectories','None','None','Allow')))
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity,'Modify','ContainerInherit,ObjectInherit','InheritOnly','Allow')))
    }elseif($Definition.researcher){$acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($ResearcherSid)),$Definition.researcher,'ContainerInherit,ObjectInherit','None','Allow')))}
    return $acl
}
function Test-GNETClientBoundaryPreflight {
    if(Test-Path -LiteralPath 'C:\ProgramData\GNETBroker\config.json'){throw 'Existing deployed broker preserved; use a reviewed upgrade instead'}
    $planned=@(Get-GNETClientBoundaryPlan|ForEach-Object {$_.path})
    foreach($path in $planned){
        if(-not (Test-Path -LiteralPath $path)){continue}
        $item=Get-Item -LiteralPath $path
        if(-not $item.PSIsContainer -or $item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Existing boundary is not a regular directory'}
        foreach($child in @(Get-ChildItem -LiteralPath $path -Force|Select-Object -First 30)){
            if($child.FullName -notin $planned){throw 'Nonempty or unrelated existing boundary preserved; preparation requires review'}
        }
    }
}
function Test-GNETClientBoundaryAcl {
    param($Actual,$Expected)
    # Windows may add only the administrative auto-inherited DACL flag.
    # Keep owner, protection, ACE identity/type/rights/order/inheritance exact.
    $gnetActual=$Actual.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]'Owner,Access')
    $gnetExpected=$Expected.GetSecurityDescriptorSddlForm([Security.AccessControl.AccessControlSections]'Owner,Access')
    $gnetActual=[regex]::Replace($gnetActual,'D:PAI(?=\(|$)','D:P')
    $gnetExpected=[regex]::Replace($gnetExpected,'D:PAI(?=\(|$)','D:P')
    return $gnetActual -ceq $gnetExpected
}
function Invoke-GNETClientBoundaries {
    param([string]$BrokerSid,[string]$ResearcherSid)
    Test-GNETClientBoundaryPreflight
    $plan=@(Get-GNETClientBoundaryPlan)
    # Refuse to change a pre-existing, differently protected folder. Validate all
    # existing targets before any new directory or ACL is created.
    foreach($definition in $plan){
        if(Test-Path -LiteralPath $definition.path){
            $expected=New-GNETClientBoundaryAcl $definition $BrokerSid $ResearcherSid
            if(-not (Test-GNETClientBoundaryAcl (Get-Acl -LiteralPath $definition.path) $expected)){throw 'Existing boundary ACL differs; no automatic adoption or repair'}
        }
    }
    $created=0
    foreach($definition in $plan){
        $expected=New-GNETClientBoundaryAcl $definition $BrokerSid $ResearcherSid
        if(-not (Test-Path -LiteralPath $definition.path)){
            New-Item -ItemType Directory -Path $definition.path|Out-Null
            Set-Acl -LiteralPath $definition.path -AclObject $expected;$created++
        }
        if(-not (Test-GNETClientBoundaryAcl (Get-Acl -LiteralPath $definition.path) $expected)){throw 'Boundary ACL verification failed; preparation incomplete'}
    }
    return @{boundaries_verified=12;directories_created=$created;research_permissions_granted=$true;broker_activated=$false;tasks_registered=$false;isolation_certified=$false}
}
if($FunctionsOnly){return}
$plan=@(Get-GNETClientBoundaryPlan)
if(-not $Apply){@{phase='preparation_only';researcher=$ResearcherIdentity;boundaries=$plan;tasks_registered=$false;broker_activated=$false}|ConvertTo-Json -Depth 5;return}
if(-not $PSCmdlet.ShouldProcess('Twelve new GNET folders for the researcher and standard broker','Prepare Windows permission boundaries; do not alter existing deployments')){return}
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'Use Administrator PowerShell'}
$account=Get-LocalUser -Name 'GNETDataBroker' -ErrorAction Stop
if(@(Get-LocalGroupMember -SID 'S-1-5-32-544').SID.Value -contains $account.SID.Value){throw 'Broker must be a standard account'}
$researcherSid=(New-Object Security.Principal.NTAccount($ResearcherIdentity)).Translate([Security.Principal.SecurityIdentifier]).Value
Invoke-GNETClientBoundaries $account.SID.Value $researcherSid|ConvertTo-Json -Depth 4

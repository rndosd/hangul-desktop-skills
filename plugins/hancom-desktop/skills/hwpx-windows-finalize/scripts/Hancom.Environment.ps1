function Get-HancomSecuritySha256([string]$Path){
    $stream=[IO.File]::OpenRead($Path);$algorithm=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','')}
    finally{$stream.Dispose();$algorithm.Dispose()}
}
# Shared per-desktop configuration. Never downloads, loads a DLL, or changes registry values.
function Get-HancomPeMachine([string]$Path){
    $s=[IO.File]::OpenRead($Path);$r=New-Object IO.BinaryReader($s)
    try{if($r.ReadUInt16() -ne 0x5A4D){throw 'Invalid executable header'};$s.Position=0x3C;$o=$r.ReadUInt32();$s.Position=$o;if($r.ReadUInt32() -ne 0x4550){throw 'Invalid PE header'};return ('0x{0:X4}' -f $r.ReadUInt16())}finally{$r.Dispose();$s.Dispose()}
}
function Get-HancomDesktopInstallation {
    foreach($view in @([Microsoft.Win32.RegistryView]::Registry32,[Microsoft.Win32.RegistryView]::Registry64)){
        $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::ClassesRoot,$view)
        try{
            $id=$base.OpenSubKey('HWPFrame.HwpObject\CLSID',$false);if(!$id){continue}
            try{$clsid=$id.GetValue('')}finally{$id.Dispose()}
            $server=$base.OpenSubKey(('CLSID\'+$clsid+'\LocalServer32'),$false);if(!$server){continue}
            try{$command=[string]$server.GetValue('')}finally{$server.Dispose()}
            if($command -match '^"?(.+?\.exe)"?(?:\s|$)'){
                $path=$Matches[1]
                if(Test-Path -LiteralPath $path -PathType Leaf){return @{path=$path;version=(Get-Item -LiteralPath $path).VersionInfo.FileVersion;machine=(Get-HancomPeMachine $path);registryView=[string]$view;clsid=$clsid}}
            }
        }finally{$base.Dispose()}
    }
    return $null
}
function Get-HancomRegisteredModule([string]$Name){
    $installation=Get-HancomDesktopInstallation
    $view=if($installation -and $installation.machine -eq '0x8664'){[Microsoft.Win32.RegistryView]::Registry64}else{[Microsoft.Win32.RegistryView]::Registry32}
    $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$view)
    try{
        $key=$base.OpenSubKey('Software\HNC\HwpAutomation\Modules',$false)
        if(!$key){return $null}
        try{if($Name -notin $key.GetValueNames()){return $null};$r=@{name=$Name;kind=[string]$key.GetValueKind($Name);path=$key.GetValue($Name,$null,[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames);uses=$null}}finally{$key.Dispose()}
        $uses=$base.OpenSubKey('Software\HNC\HwpAutomation\Modules\Uses',$false)
        if($uses){try{$r.uses=$uses.GetValue($Name,$null)}finally{$uses.Dispose()}}
        return $r
    }finally{$base.Dispose()}
}
function Get-HancomEnvironment {
    $path=Join-Path (Split-Path $PSScriptRoot -Parent) 'environment.json'
    if(!(Test-Path -LiteralPath $path)){
        $root=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}
        $path=Join-Path $root 'skills/hwpx-windows-finalize/environment.json'
    }
    if(!(Test-Path -LiteralPath $path)){throw 'DESKTOP_NOT_CONFIGURED: run Install-HangulSkills.ps1 first.'}
    return (Get-Content -LiteralPath $path -Raw -Encoding UTF8|ConvertFrom-Json)
}
function Assert-HancomSecurityBinding($Environment){
    $s=$Environment.security
    if(!$s -or $s.status -ne 'reviewed_existing' -or $s.reviewConfirmed -ne $true){throw 'SECURITY_MODULE_NOT_CONFIGURED: select an existing module only after provenance and access-policy review. No DLL was loaded.'}
    if(!$s.moduleName -or !$s.dllPath -or $s.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or !$s.policyPath -or $s.policySha256 -notmatch '^[0-9a-fA-F]{64}$'){throw 'SECURITY_METADATA_INCOMPLETE'}
    $registered=Get-HancomRegisteredModule $s.moduleName
    if(!$registered -or $registered.kind -ne 'String' -or !$registered.path -or ![IO.Path]::IsPathRooted($registered.path)){throw 'SECURITY_REGISTRY_MISMATCH'}
    if([IO.Path]::GetFullPath($registered.path) -ine [IO.Path]::GetFullPath($s.dllPath)){throw 'SECURITY_REGISTRY_PATH_CHANGED'}
    if($null -ne $registered.uses -and $registered.uses -eq 0){throw 'SECURITY_MODULE_DISABLED'}
    if(!(Test-Path -LiteralPath $s.dllPath -PathType Leaf) -or (Get-HancomSecuritySha256 $s.dllPath) -ine $s.sha256){throw 'SECURITY_DLL_HASH_MISMATCH'}
    if(!(Test-Path -LiteralPath $s.policyPath -PathType Leaf) -or (Get-HancomSecuritySha256 $s.policyPath) -ine $s.policySha256){throw 'SECURITY_POLICY_EVIDENCE_CHANGED'}
    $hancom=Get-HancomDesktopInstallation
    if(!$hancom -or (Get-HancomPeMachine $s.dllPath) -ne $hancom.machine){throw 'SECURITY_DLL_ARCHITECTURE_MISMATCH'}
    return $s.moduleName
}

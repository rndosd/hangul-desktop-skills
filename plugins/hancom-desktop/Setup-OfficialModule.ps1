[CmdletBinding()]
param([switch]$AcceptGlobalFileAccess,[string]$CodexRoot,[string]$PythonPath,[string]$ArchivePath)
$ErrorActionPreference='Stop'
if(!$AcceptGlobalFileAccess){throw 'Explicit consent required: -AcceptGlobalFileAccess. Official example permits all requested paths within your Windows permissions.'}
if(!$CodexRoot){$CodexRoot=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}}
. (Join-Path $PSScriptRoot 'skills/hwpx-windows-finalize/scripts/Hancom.Environment.ps1')
$hancom=Get-HancomDesktopInstallation
if(!$hancom){throw 'Install and activate a licensed Windows Hancom Hangul first.'}
if($hancom.machine -ne '0x014C'){throw 'This pinned official DLL is x86. No compatible official x64 binary has been validated; registration stopped.'}
if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count){throw 'Save and close Hangul before setup.'}
if(!$PythonPath){
 $probe=& powershell.exe -NoProfile -File (Join-Path $PSScriptRoot 'Install-HangulSkills.ps1') -CodexRoot $CodexRoot -CheckOnly
 if($LASTEXITCODE -ne 0){throw 'Environment preflight failed'}
 $environment=$probe|ConvertFrom-Json
 if(!$environment.pythonPath){$PythonPath=(& (Join-Path $PSScriptRoot 'Bootstrap-Python.ps1') -CodexRoot $CodexRoot|Select-Object -Last 1)}
}
$folder=Join-Path $CodexRoot 'runtimes/hancom-official/9ac5b97c47ac8aed'
New-Item -ItemType Directory -Path $folder -Force|Out-Null
$url='https://github.com/hancom-io/devcenter-archive/raw/main/hwp-automation/%EB%B3%B4%EC%95%88%EB%AA%A8%EB%93%88%28Automation%29.zip'
$zip=Join-Path $folder 'official-source.zip'
if($ArchivePath){Copy-Item -LiteralPath $ArchivePath -Destination $zip -Force}else{Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip}
if((Get-HancomSecuritySha256 $zip) -ine '5d87292efafd7311cba6d35e4b416ac8bfa78608a64dde1656c8cb827b051bd8'){throw 'Official archive changed; review required.'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$dll=Join-Path $folder 'FilePathCheckerModuleExample.dll'
$archive=[IO.Compression.ZipFile]::OpenRead($zip)
try{$entry=$archive.GetEntry('FilePathCheckerModuleExample.dll');if(!$entry){throw 'DLL member missing'};[IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$dll,$true)}finally{$archive.Dispose()}
$hash=Get-HancomSecuritySha256 $dll
if($hash -ine '9ac5b97c47ac8aed1e8bca27a3eef39411361d8f68c262509f0c40a8f9d21bb6' -or (Get-HancomPeMachine $dll) -ne '0x014C'){throw 'DLL validation failed'}
$policy=Join-Path $folder 'reviewed-policy.txt'
[IO.File]::WriteAllText($policy,"Official Hancom Automation example. Source: $url`r`nDLL SHA256: $hash`r`nThe accompanying source immediately returns TRUE from IsAccessiblePath. Global access explicitly accepted by this user. No folder restriction. Binary/source equivalence not independently proven. Windows permissions still apply. Not an OS sandbox.",[Text.Encoding]::UTF8)
$base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
$key=$base.CreateSubKey('Software\HNC\HwpAutomation\Modules')
$name='FilePathCheckerModuleExample'
$exists=$name -in $key.GetValueNames()
$backup=[ordered]@{name=$name;existed=$exists;oldValue=if($exists){$key.GetValue($name)}else{$null};oldKind=if($exists){[string]$key.GetValueKind($name)}else{$null};newValue=$dll;view='Registry32';createdAt=(Get-Date).ToString('o')}
$receipt=Join-Path $folder ('registration-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.json')
$backup|ConvertTo-Json|Set-Content -LiteralPath $receipt -Encoding UTF8
try{$key.SetValue($name,$dll,[Microsoft.Win32.RegistryValueKind]::String)}finally{$key.Dispose();$base.Dispose()}
$argsMap=@{CodexRoot=$CodexRoot;SecurityModuleName=$name;SecurityDllSha256=$hash;SecurityPolicyPath=$policy;ConfirmReviewedSecurityModule=$true}
if($PythonPath){$argsMap.PythonPath=$PythonPath}
try{
 & (Join-Path $PSScriptRoot 'Install-HangulSkills.ps1') @argsMap
 if(!$?){throw 'Skill setup failed'}
}catch{
 $b=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
 $k=$b.OpenSubKey('Software\HNC\HwpAutomation\Modules',$true)
 try{if($k.GetValue($name) -eq $dll){if($exists){$k.SetValue($name,$backup.oldValue,[Microsoft.Win32.RegistryValueKind]::$($backup.oldKind))}else{$k.DeleteValue($name)}}}finally{$k.Dispose();$b.Dispose()}
 throw ('Skill setup failed; registry value restored. Receipt: '+$receipt+'; '+$_.Exception.Message)
}
Write-Output ('Registration backup: '+$receipt)
Write-Output 'Next: run installed check_hancom_com.ps1. COM creation and RegisterModule success are separate checks.'

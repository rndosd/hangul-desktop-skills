param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputPath){throw 'New context output required'}
. (Join-Path $PSScriptRoot 'Hancom.Environment.ps1')
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
$result=[ordered]@{status='BLOCKED_PREFLIGHT';comCalled=$false;sessionId=(Get-Process -Id $PID).SessionId;isSystem=$identity.IsSystem;isAdministrator=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);apartment=[Threading.Thread]::CurrentThread.GetApartmentState().ToString();installation=$null;securityBinding=$null;settingsChanged=$false;error=$null}
try{
 if($result.isSystem -or $result.isAdministrator -or $result.sessionId -eq 0){throw 'NORMAL_LOGGED_IN_USER_REQUIRED'}
 $environment=Get-HancomEnvironment
 $result.installation=Get-HancomDesktopInstallation
 if(!$result.installation -or [IO.Path]::GetFullPath($result.installation.path) -ine [IO.Path]::GetFullPath($environment.hancom.path) -or $result.installation.version -ne $environment.hancom.version -or $result.installation.machine -ne $environment.hancom.machine){throw 'DESKTOP_INSTALLATION_CHANGED: refresh per-PC configuration; no registry repair was attempted'}
 $result.securityBinding=Assert-HancomSecurityBinding $environment
 if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -ne 0){throw 'PROCESS_CONFLICT: existing Hangul process; no COM call'}
 $result.status='PASS_PREFLIGHT_NATIVE_NOT_CALLED'
}catch{$result.error=$_.Exception.Message}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($result|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
if($result.status -ne 'PASS_PREFLIGHT_NATIVE_NOT_CALLED'){exit 3}

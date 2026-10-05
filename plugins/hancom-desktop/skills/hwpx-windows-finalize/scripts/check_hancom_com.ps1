[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Hancom.Environment.ps1')
$hwp=$null
$result=[ordered]@{available=$false;comCreated=$false;registerModuleCalled=$false;securityModuleRegistered=$null;moduleName=$null;version=$null;status='BLOCKED_COM';reasonCode=$null;error=$null}
try{
    if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count){$result.reasonCode='PROCESS_CONFLICT';throw 'Existing Hangul process; no COM probe issued.'}
    $hwp=New-Object -ComObject HWPFrame.HwpObject
    $result.comCreated=$true
    try{$result.version=[string]$hwp.Version}catch{}
    $result.status='BLOCKED_SECURITY'
    $result.moduleName=Assert-HancomSecurityBinding (Get-HancomEnvironment)
    $result.registerModuleCalled=$true
    $result.securityModuleRegistered=[bool]$hwp.RegisterModule('FilePathCheckDLL',[string]$result.moduleName)
    if(!$result.securityModuleRegistered){$result.reasonCode='REGISTER_MODULE_RETURNED_FALSE';throw 'The selected reviewed module returned false; no document was opened.'}
    $result.available=$true;$result.status='PASS_COM_AND_SECURITY'
}catch{
    if(!$result.reasonCode){$result.reasonCode=if($result.comCreated){'SECURITY_PREFLIGHT_FAILED'}else{'COM_UNAVAILABLE'}}
    $result.error=$_.Exception.Message
}finally{
    if($null -ne $hwp){try{$hwp.Quit()}catch{};try{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp)}catch{}}
}
$result|ConvertTo-Json -Depth 5
if(!$result.available){exit 2}

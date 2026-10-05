# Pure guard regression; no COM instance is created.
. (Join-Path $PSScriptRoot 'Hancom.Cell.Common.ps1')
Assert-SelectCtrlResult $true 'other'
Assert-SelectCtrlResult $false '13, 0, 0, 653'
foreach($case in @(@{value=$false;version='13, 0, 0, 654'},@{value=$null;version='13, 0, 0, 653'})){
 $blocked=$false
 try {Assert-SelectCtrlResult $case.value $case.version} catch {$blocked=$_.Exception.Message.StartsWith('RETURN_FALSE:')}
 if(!$blocked){throw 'Unexpected SelectCtrl result accepted'}
}
'PASS_VERSION_GUARD'

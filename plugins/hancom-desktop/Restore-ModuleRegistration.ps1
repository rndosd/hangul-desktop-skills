param([Parameter(Mandatory=$true)][string]$ReceiptPath,[switch]$Apply)
$ErrorActionPreference='Stop'
$r=Get-Content -LiteralPath $ReceiptPath -Raw -Encoding UTF8|ConvertFrom-Json
if($r.name -ne 'FilePathCheckerModuleExample' -or $r.view -ne 'Registry32'){throw 'Unexpected receipt'}
if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count){throw 'Close Hangul first'}
$b=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
try{
 $k=$b.OpenSubKey('Software\HNC\HwpAutomation\Modules',[bool]$Apply)
 if(!$k){throw 'Registry key missing'}
 try{
  if($k.GetValue($r.name) -ne $r.newValue){throw 'Value changed since installation; no change made'}
  if($Apply){if($r.existed){$k.SetValue($r.name,$r.oldValue,[Microsoft.Win32.RegistryValueKind]::$($r.oldKind))}else{$k.DeleteValue($r.name)}}
  [pscustomobject]@{applied=[bool]$Apply;name=$r.name;restore=$r.oldValue;removeValue=(!$r.existed)}|ConvertTo-Json
 }finally{$k.Dispose()}
}finally{$b.Dispose()}

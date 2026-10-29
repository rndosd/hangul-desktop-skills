[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ProgressPath,
    [Parameter(Mandatory=$true)][string]$ExpectedDocumentPath,
    [Parameter(Mandatory=$true)][string]$Moniker,
    [Parameter(Mandatory=$true)][string]$LogPath,
    [int]$WorkerProcessId,
    [long]$WorkerStartTicks
)
$ErrorActionPreference='Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class RecordedRotOwner {
    [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int reserved, out IRunningObjectTable table);
    [DllImport("ole32.dll")] static extern int CreateBindCtx(int reserved, out IBindCtx context);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid);
    public static object GetExisting(string expected) {
        IRunningObjectTable table=null; IBindCtx context=null; IEnumMoniker enumerator=null;
        try {
            Marshal.ThrowExceptionForHR(GetRunningObjectTable(0,out table));
            Marshal.ThrowExceptionForHR(CreateBindCtx(0,out context));
            table.EnumRunning(out enumerator);
            var monikers=new IMoniker[1];
            while(enumerator.Next(1,monikers,IntPtr.Zero)==0) {
                try {
                    string name;monikers[0].GetDisplayName(context,null,out name);
                    if(name==expected){object value;Marshal.ThrowExceptionForHR(table.GetObject(monikers[0],out value));return value;}
                } finally { Marshal.ReleaseComObject(monikers[0]); }
            }
            throw new InvalidOperationException("RECORDED_MONIKER_ABSENT");
        } finally {
            if(enumerator!=null)Marshal.ReleaseComObject(enumerator);
            if(context!=null)Marshal.ReleaseComObject(context);
            if(table!=null)Marshal.ReleaseComObject(table);
        }
    }
}
'@
$rows=@(Get-Content -LiteralPath $ProgressPath -Encoding UTF8 | ForEach-Object {$_|ConvertFrom-Json})
$evidence=$rows[-1]
$recorded=$evidence.owner
if(!$recorded -or !$evidence.comCreated -or !$evidence.securityModuleRegistered -or [long]$recorded.pid -le 0 -or [long]$recorded.startTicks -le 0 -or [long]$recorded.hwnd -le 0 -or !$recorded.path){throw 'OWNER_EVIDENCE_INCOMPLETE'}
$workerIdentity=if($evidence.worker){$evidence.worker}else{@{pid=$WorkerProcessId;startTicks=$WorkerStartTicks}}
if([long]$workerIdentity.pid -le 0 -or [long]$workerIdentity.startTicks -le 0){throw 'WORKER_IDENTITY_REQUIRED: use the recorded controller worker identity for legacy progress.'}
function Assert-WorkerExited {
    $active=$null
    try {$active=Get-Process -Id ([int]$workerIdentity.pid) -ErrorAction Stop}
    catch {if($_.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId,*'){throw}}
    if($null -ne $active){
        try {
            $null=$active.Handle
            if(!$active.HasExited -and $active.StartTime.ToUniversalTime().Ticks -eq [long]$workerIdentity.startTicks){throw 'WORKER_STILL_RUNNING: do not recover concurrently.'}
        } finally {$active.Dispose()}
    }
}
$expected=(Resolve-Path -LiteralPath $ExpectedDocumentPath).Path
$documentPath=$null
function Assert-RecordedOwner {
    $active=Get-Process -Id ([int]$recorded.pid) -ErrorAction Stop
    try {
        $null=$active.Handle
        if($active.HasExited -or $active.StartTime.ToUniversalTime().Ticks -ne ([long]$recorded.startTicks) -or $active.Path -ine ([string]$recorded.path) -or $active.ProcessName -ne 'Hwp'){throw 'OWNER_MISMATCH'}
    } finally {$active.Dispose()}
}
$log=[IO.Path]::GetFullPath($LogPath)
if(Test-Path -LiteralPath $log){throw 'NEW_LOG_REQUIRED'}
function Record([string]$stage){[IO.File]::AppendAllText($log,((@{stage=$stage;utc=[DateTime]::UtcNow.ToString('o');pid=([int]$recorded.pid);startTicks=([long]$recorded.startTicks);hwnd=([long]$recorded.hwnd);newCOMCreated=$false;forced=$false;documentPath=$documentPath}|ConvertTo-Json -Compress)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))}
$hwp=$null
try {
    Assert-WorkerExited
    Assert-RecordedOwner
    Record 'bind-existing-start'
    $hwp=[RecordedRotOwner]::GetExisting($Moniker)
    Record 'bind-existing-done'
    $hwnd=[IntPtr]([long]$hwp.XHwpWindows.Item(0).WindowHandle)
    [uint32]$windowPid=0
    $null=[RecordedRotOwner]::GetWindowThreadProcessId($hwnd,[ref]$windowPid)
    if($hwnd.ToInt64() -ne ([long]$recorded.hwnd) -or $windowPid -ne ([int]$recorded.pid)){throw 'WINDOW_OWNER_MISMATCH'}
    Assert-RecordedOwner
    $documents=$hwp.XHwpDocuments
    if([int]$documents.Count -ne 1){throw 'DOCUMENT_COUNT_MISMATCH'}
    $documentPath=[string]$documents.Item(0).FullName
    if([string]::IsNullOrWhiteSpace($documentPath) -or [IO.Path]::GetFullPath($documentPath) -ine $expected){throw 'DOCUMENT_PATH_MISMATCH'}
    Record 'document-verified'
    Assert-RecordedOwner
    Record 'clear-start'
    $hwp.Clear(1)
    Record 'clear-done'
    Assert-RecordedOwner
    Record 'quit-start'
    $hwp.Quit()
    Record 'quit-done'
} catch {Record ('blocked-'+$_.Exception.Message);throw}
finally {if($null -ne $hwp){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp)}}
. (Join-Path $PSScriptRoot 'Hancom.OwnedExit.ps1')
$result=Wait-HancomOwnedExit -Owner @{pid=([int]$recorded.pid);startTicks=([long]$recorded.startTicks);path=([string]$recorded.path)} -LimitMs 10000
$result|ConvertTo-Json
Record ('exit-observed-'+$result.exited)
if($result.exited -ne $true){throw 'NORMAL_EXIT_UNCONFIRMED'}

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$EvidenceDirectory,
    [Parameter(Mandatory=$true)][string]$BaselineController
)
$ErrorActionPreference='Stop'
$null=New-Item -ItemType Directory -Path $EvidenceDirectory -ErrorAction Stop
$EvidenceDirectory=(Resolve-Path -LiteralPath $EvidenceDirectory).Path
function Import-Functions([string]$Path,[string[]]$Names) {
    $tokens=$null;$errors=$null
    $ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors)
    if($errors.Count){throw ($errors|Out-String)}
    foreach($name in $Names){
        $function=$ast.Find({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)
        if(!$function){throw "MISSING_FUNCTION $name"}
        . ([scriptblock]::Create($function.Extent.Text.Replace("function $name", "function script:$name")))
    }
    return $ast
}
$controller=Import-Functions (Join-Path $PSScriptRoot 'verify_hwpx_with_hancom.ps1') @('Get-HancomInterruptedReceipt','Write-Receipt','Get-HancomSourceSha256')
$worker=Import-Functions (Join-Path $PSScriptRoot 'hancom_worker.ps1') @('Write-HancomStage','Close-HancomObject')
$recovery=Import-Functions (Join-Path $PSScriptRoot 'Recover-HancomOwnedInstance.ps1') @('Assert-RecordedOwner','Assert-WorkerExited')
function Get-Process {param($Name,$Id,$ErrorAction);throw 'REAL_PROCESS_LOOKUP_FORBIDDEN_IN_FIXTURE'}
$Mode='SaveAs';$TimeoutSeconds=20
$candidate=Join-Path $EvidenceDirectory 'candidate.hwpx';[IO.File]::WriteAllText($candidate,'unchanged source fixture')
$sourceHashBefore=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
$OutputPath=Join-Path $EvidenceDirectory 'output.hwpx';$PdfPath=$null
$progressPath=Join-Path $EvidenceDirectory 'progress.jsonl'
$owner=@{pid=12345;startTicks=639000000000000000;path='C:\fixture\Hwp.exe';hwnd=999}
$snapshot=@{status='BLOCKED_COM';firstOpen=$true;saveAs=$false;reopen=$false;pageCountBefore=2}
$row=@{stage='hwpx-save-start';receipt=$snapshot;owner=$owner;comCreated=$true;registerModuleCalled=$true;securityModuleRegistered=$true;normalQuit=$false;elapsedMs=500}
[IO.File]::WriteAllText($progressPath,(($row|ConvertTo-Json -Depth 6 -Compress)+"`n"+'{"truncated":'))
function Get-Process {param($Name,$Id,$ErrorAction);[pscustomobject]@{Id=12345}}
$result=Get-HancomInterruptedReceipt $progressPath 'fixture timeout'
if($result.firstOpen -ne $true -or $result.comCreated -ne $true -or $result.cleanup.owner.pid -ne 12345 -or $result.progress.lastStage -ne 'hwpx-save-start' -or $result.progress.invalidRows -ne 1 -or $result.status -ne 'BLOCKED_COM' -or $result.inFlightOutcome -ne 'UNKNOWN_DO_NOT_RETRY' -or !$result.sourceUnchanged){throw 'INTERRUPTED_EVIDENCE_CONTRACT'}
$cases=@(@{name='timeout-retains-last-complete-observation';status='PASS';observed=$result})
$missing=Get-HancomInterruptedReceipt (Join-Path $EvidenceDirectory 'absent.jsonl') 'fixture missing receipt'
if($null -ne $missing.firstOpen -or $null -ne $missing.comCreated -or $missing.cleanup.owned){throw 'MISSING_EVIDENCE_IS_UNKNOWN'}
$cases+=@{name='missing-progress-does-not-invent-false';status='PASS'}
[IO.File]::WriteAllText($OutputPath,'partial output')
[IO.File]::WriteAllText($candidate,'changed source fixture')
$changed=Get-HancomInterruptedReceipt $progressPath 'fixture timeout'
if($changed.sourceUnchanged -or $changed.artifacts.Count -ne 1 -or $changed.artifacts[0].completion -ne 'UNVERIFIED'){throw 'INTERRUPTED_ARTIFACT_CONTRACT'}
$cases+=@{name='changed-source-and-partial-output-stay-unverified';status='PASS'}
$existingCandidate=$candidate
$candidate=Join-Path $EvidenceDirectory 'missing-source.hwpx'
$unreadable=Get-HancomInterruptedReceipt $progressPath 'fixture vanished source'
if($null -ne $unreadable.sourceUnchanged -or $unreadable.observationErrors.Count -ne 1 -or $unreadable.observationErrors[0].operation -ne 'source-hash' -or $unreadable.firstOpen -ne $true){throw 'MISSING_SOURCE_MUST_PRESERVE_INTERRUPTED_RECEIPT'}
$candidate=$existingCandidate
$cases+=@{name='missing-source-still-produces-interrupted-receipt';status='PASS'}
$timeoutIf=$controller.Find({param($node)$node -is [Management.Automation.Language.IfStatementAst] -and $node.Clauses[0].Item1.Extent.Text -like '*WaitForExit($TimeoutSeconds * 1000)*'},$true)
if(!$timeoutIf){throw 'CONTROLLER_TIMEOUT_BRANCH_MISSING'}
$timeoutBody=$timeoutIf.Clauses[0].Item2.Statements|Where-Object{$_ -isnot [Management.Automation.Language.ExitStatementAst]}|ForEach-Object{$_.Extent.Text}
$timeoutBlock=[scriptblock]::Create($timeoutBody -join "`n")
$cancellationPath=Join-Path $EvidenceDirectory 'controller.cancel'
$ReceiptPath=Join-Path $EvidenceDirectory 'controller-receipt.json'
$temporaryReceipt=Join-Path $EvidenceDirectory 'worker-receipt.json'
$workerIdentity=@{pid=6789;startTicks=639000000000000001}
$process=[pscustomobject]@{waitMs=0}
$process|Add-Member ScriptMethod WaitForExit {param($ms);$this.waitMs=$ms;return $false}
$null=. $timeoutBlock
$timed=Get-Content -LiteralPath $ReceiptPath -Raw|ConvertFrom-Json
if(!(Test-Path -LiteralPath $cancellationPath) -or $process.waitMs -ne 5000 -or $timed.worker.exited -ne $false -or $timed.worker.forced -ne $false -or $timed.firstOpen -ne $true -or $timed.status -ne 'BLOCKED_COM'){throw 'TIMEOUT_CANCELLATION_AND_RECEIPT_CONTRACT'}
$cases+=@{name='actual-controller-timeout-requests-cancel-and-preserves-live-worker';status='PASS'}
$original=[IO.File]::ReadAllText($BaselineController)
$begin=$original.IndexOf('        $receipt = [ordered]@{')
$end=$original.IndexOf('        Write-Receipt $receipt $ReceiptPath',$begin)
. ([scriptblock]::Create($original.Substring($begin,$end-$begin)))
if($receipt.firstOpen -ne $false){throw 'BASELINE_TIMEOUT_DEFECT_NOT_REPRODUCED'}
$cases+=@{name='baseline-erases-observed-firstOpen';status='REPRODUCED_FAILURE';observedFirstOpen=$receipt.firstOpen;actualFirstOpen=$true}
$ProgressPath=Join-Path $EvidenceDirectory 'cancel-progress.jsonl'
$CancellationPath=Join-Path $EvidenceDirectory 'cancel.marker';[IO.File]::WriteAllText($CancellationPath,'cancel')
$script:StageClock=[Diagnostics.Stopwatch]::StartNew();$script:LastStageMs=0;$script:Closing=$false
$script:ComCreated=$true;$script:RegisterModuleCalled=$true;$script:SecurityModuleRegistered=$true;$script:RegisterModuleName='fixture'
$script:Owned=$true;$script:Owner=$owner;$script:NormalQuit=$false;$receipt=@{status='BLOCKED_COM';firstOpen=$true}
$cancelled=$false
try{Write-HancomStage 'first-open-done'}catch{if($_.Exception.Message -like 'CANCELLED_BY_CONTROLLER*'){$cancelled=$true}else{throw}}
if(!$cancelled -or !$receipt.cancellationRequested){throw 'CANCELLATION_CHECKPOINT_CONTRACT'}
$fake=[pscustomobject]@{clearCalls=0;quitCalls=0}
$fake|Add-Member ScriptMethod Clear {param($mode);if($mode -ne 1){throw 'WRONG_CLEAR_MODE'};$this.clearCalls++}
$fake|Add-Member ScriptMethod Quit {$this.quitCalls++}
Close-HancomObject $fake
if($fake.clearCalls -ne 1 -or $fake.quitCalls -ne 1 -or !$script:NormalQuit){throw 'NORMAL_CLEANUP_AFTER_CANCELLATION'}
$cases+=@{name='cancellation-stops-at-checkpoint-and-runs-normal-clear-quit';status='PASS'}
Add-Type -TypeDefinition @'
using System;
public static class RecordedRotOwner {
    public static object Target;
    public static uint WindowPid=12345;
    public static int BindCalls=0;
    public static object GetExisting(string moniker){BindCalls++;return Target;}
    public static uint GetWindowThreadProcessId(IntPtr hwnd,out uint pid){pid=WindowPid;return 1;}
}
'@
$mainTry=$recovery.Find({param($node)$node -is [Management.Automation.Language.TryStatementAst] -and $node.Body.Extent.Text.Contains('GetExisting($Moniker)')},$true)
if(!$mainTry){throw 'RECOVERY_BODY_MISSING'}
$body=$mainTry.Body.Extent.Text
$recover=[scriptblock]::Create($body.Substring(1,$body.Length-2))
function Record([string]$stage){}
function Get-Process {
    param($Name,$Id,$ErrorAction)
    if($Id -eq 6789 -and !$script:workerAlive){return $null}
    if($Id -eq 6789){
        $p=[pscustomobject]@{Handle=[IntPtr]1;HasExited=$false;StartTime=[datetime]::new(639000000000000001,[DateTimeKind]::Utc)}
        $p|Add-Member ScriptMethod Dispose {}
        return $p
    }
    if($Id -ne 12345){throw 'UNEXPECTED_PROCESS_LOOKUP'}
    $p=[pscustomobject]@{Handle=[IntPtr]1;HasExited=$false;StartTime=[datetime]::new($script:fixtureTicks,[DateTimeKind]::Utc);Path='C:\fixture\Hwp.exe';ProcessName='Hwp'}
    $p|Add-Member ScriptMethod Dispose {}
    return $p
}
$recorded=[pscustomobject]$owner;$expected=$candidate;$Moniker='fixture-moniker'
$workerIdentity=@{pid=6789;startTicks=639000000000000001}
foreach($mode in @('match','reused-pid','wrong-window','extra-document','wrong-document','live-worker')){
    $script:workerAlive=($mode -eq 'live-worker')
    $script:fixtureTicks=639000000000000000
    if($mode -eq 'reused-pid'){$script:fixtureTicks++}
    $window=[pscustomobject]@{WindowHandle=if($mode -eq 'wrong-window'){1000}else{999}}
    $windows=[pscustomobject]@{window=$window};$windows|Add-Member ScriptMethod Item {param($index);$this.window}
    $doc=[pscustomobject]@{FullName=if($mode -eq 'wrong-document'){'C:\other-user-document.hwpx'}else{$candidate}}
    $documents=[pscustomobject]@{Count=if($mode -eq 'extra-document'){2}else{1};document=$doc};$documents|Add-Member ScriptMethod Item {param($index);$this.document}
    $target=[pscustomobject]@{XHwpWindows=$windows;XHwpDocuments=$documents;clearCalls=0;quitCalls=0}
    $target|Add-Member ScriptMethod Clear {param($mode);$this.clearCalls++}
    $target|Add-Member ScriptMethod Quit {$this.quitCalls++}
    [RecordedRotOwner]::Target=$target;[RecordedRotOwner]::BindCalls=0
    $failure=$null
    try{. $recover}catch{$failure=$_.Exception.Message}
    if($mode -eq 'match'){
        if($failure -or $target.clearCalls -ne 1 -or $target.quitCalls -ne 1){throw 'MATCHED_RECOVERY_CONTRACT'}
    } else {
        if(!$failure -or $target.clearCalls -ne 0 -or $target.quitCalls -ne 0){throw "RECOVERY_TOUCHED_UNMATCHED $mode"}
        if($mode -in @('reused-pid','live-worker') -and [RecordedRotOwner]::BindCalls -ne 0){throw 'UNSAFE_WORKER_OR_PID_BOUND_OBJECT'}
    }
    $cases+=@{name=('recovery-'+$mode);status='PASS';observedError=$failure;clearCalls=$target.clearCalls;quitCalls=$target.quitCalls}
}
foreach($ast in @($controller,$worker,$recovery)) {
    $unsafe=$ast.FindAll({param($node)($node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'Stop-Process') -or ($node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and $node.Member.Value -in @('Kill','CloseMainWindow'))},$true)
    if($unsafe.Count){throw 'FORCE_TERMINATION_PRESENT'}
}
Add-Type -TypeDefinition @'
using System;
using System.Threading;
public static class WorkerLeaseFixture {
    public static ManualResetEvent Ready=new ManualResetEvent(false);
    public static ManualResetEvent Release=new ManualResetEvent(false);
    public static Thread Holder;
    public static void Start(string name) {
        Holder=new Thread(()=>{using(var gate=new Mutex(false,name)){gate.WaitOne();try{Ready.Set();Release.WaitOne();}finally{gate.ReleaseMutex();}}});
        Holder.Start();
        if(!Ready.WaitOne(3000))throw new Exception("fixture holder did not start");
    }
    public static void Stop(){Release.Set();if(!Holder.Join(3000))throw new Exception("fixture holder did not exit");}
}
'@
$mainWorkerTry=$worker.Find({param($node)$node -is [Management.Automation.Language.TryStatementAst] -and $node.Body.Extent.Text.Contains('$workerLocked=$workerMutex.WaitOne(0)')},$true)
if(!$mainWorkerTry){throw 'WORKER_LEASE_ACQUIRE_MISSING'}
$acquire=[scriptblock]::Create(($mainWorkerTry.Body.Statements[0..1]|ForEach-Object{$_.Extent.Text}) -join "`n")
$leaseName='Local\HancomFixture-'+[guid]::NewGuid().ToString('N')
[WorkerLeaseFixture]::Start($leaseName)
$workerMutex=[Threading.Mutex]::new($false,$leaseName);$workerLocked=$false
$blocked=$false
try{. $acquire}catch{if($_.Exception.Message -like 'LOCK_CONFLICT*'){$blocked=$true}else{throw}}
finally{[WorkerLeaseFixture]::Stop()}
if(!$blocked -or $workerLocked){throw 'CONCURRENT_WORKER_NOT_BLOCKED_BEFORE_COM'}
. $acquire
if(!$workerLocked){throw 'RELEASED_WORKER_LEASE_NOT_REUSABLE'}
$workerMutex.ReleaseMutex();$workerMutex.Dispose()
$cases+=@{name='live-worker-lease-blocks-second-worker-before-com';status='PASS'}
$script:Closing=$false;$cancelled=$false
try{Write-HancomStage 'com-start'}catch{if($_.Exception.Message -like 'CANCELLED_BY_CONTROLLER*'){$cancelled=$true}else{throw}}
if(!$cancelled){throw 'LATE_WORKER_IGNORED_CANCELLATION'}
$cases+=@{name='late-worker-cancels-at-com-start-before-activation';status='PASS'}
$summary=@{status='PASS';nativeCOMCalls=0;actualOSProcessLookupCalls=0;cases=$cases;scope='In-memory controller/worker behavior; native search and ROT recovery use separate real-run evidence.'}
[IO.File]::WriteAllText((Join-Path $EvidenceDirectory 'summary.json'),($summary|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
Write-Output "PASS $($cases.Count) interrupted-run cases. No native process touched."

[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BaselineController,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Hancom.OwnedExit.ps1')
$script:rows=@()
$script:owner=[pscustomobject]@{pid=9123;startTicks=639000000000000000;path='C:\Qualified\Hwp.exe'}
function New-Fake([string]$Mode) {
    $p=[pscustomobject]@{mode=$Mode;exitFlag=($Mode -eq 'already-exited');waitCalls=0;disposeCalls=0}
    $p|Add-Member ScriptProperty Handle {if($this.mode -eq 'handle-error'){throw 'fixture handle unavailable'};[IntPtr]1}
    $p|Add-Member ScriptProperty HasExited {if($this.mode -eq 'exit-error'){throw 'fixture exit unavailable'};[bool]$this.exitFlag}
    $p|Add-Member ScriptProperty StartTime {if($this.mode -eq 'read-error'){throw 'fixture metadata denied'};if($this.mode -eq 'ticks-mismatch'){[datetime]::new(639000000000000001,[DateTimeKind]::Utc)}else{[datetime]::new(639000000000000000,[DateTimeKind]::Utc)}}
    $p|Add-Member ScriptProperty ProcessName {
        if($this.mode -eq 'exit-empty-name'){$this.exitFlag=$true;return ''}
        if($this.mode -eq 'name-mismatch-exits'){$this.exitFlag=$true;return 'OtherApp'}
        if($this.mode -eq 'name-mismatch'){return 'OtherApp'}
        if($this.mode -eq 'live-empty-name'){return ''}
        'Hwp'
    }
    $p|Add-Member ScriptProperty Path {if($this.mode -eq 'exit-path-error'){$this.exitFlag=$true;throw 'fixture process exited'};if($this.mode -eq 'path-mismatch'){'C:\Other\Hwp.exe'}else{'C:\Qualified\Hwp.exe'}}
    $p|Add-Member ScriptMethod WaitForExit {param($ms);$this.waitCalls++;if($this.mode -eq 'timeout'){return $false};if($this.mode -eq 'wait-error'){throw 'fixture wait unavailable'};if($this.mode -eq 'wait-exits-error'){$this.exitFlag=$true;throw 'fixture exit during wait'};$this.exitFlag=$true;return $true}
    $p|Add-Member ScriptMethod Dispose {$this.disposeCalls++}
    return $p
}
function Assert-Case([string]$Name,[string]$Mode,[bool]$Blocked,[bool]$Exited,[int]$WaitCalls,[string]$Observation='') {
    $script:fake=New-Fake $Mode
    $a=Wait-HancomOwnedExit -Owner $script:owner -ProcessLookup {param($ProcessId);if($ProcessId -ne 9123){throw 'wrong PID'};$script:fake}
    if ([bool]$a.identityError -ne $Blocked -or ($a.exited -eq $true) -ne $Exited -or $script:fake.waitCalls -ne $WaitCalls -or $script:fake.disposeCalls -ne 1 -or ($Observation -and $a.exitObservation -ne $Observation)) {throw "Failed $Name : $($a|ConvertTo-Json -Compress)"}
    $script:rows+=@{name=$Name;expectedBlocked=$Blocked;expectedExited=$Exited;expectedWaitCalls=$WaitCalls;observed=$a;waitCalls=$script:fake.waitCalls;disposeCalls=$script:fake.disposeCalls;status='PASS'}
}
# Independent observable contracts: no waits for unmatched/unknown instances.
Assert-Case 'matching-live-instance-exits' 'normal' $false $true 1 'MATCHED_INSTANCE_EXITED'
Assert-Case 'handle-already-exited' 'already-exited' $false $true 0 'HANDLE_EXITED_BEFORE_IDENTITY'
Assert-Case 'exit-between-lookup-and-name-read' 'exit-empty-name' $false $true 0 'HANDLE_EXITED_DURING_IDENTITY'
Assert-Case 'exit-during-path-read' 'exit-path-error' $false $true 0 'HANDLE_EXITED_DURING_IDENTITY'
Assert-Case 'live-name-mismatch' 'name-mismatch' $true $false 0
Assert-Case 'known-name-mismatch-even-if-exits' 'name-mismatch-exits' $true $false 0
Assert-Case 'reused-PID-start-time-mismatch' 'ticks-mismatch' $true $false 0
Assert-Case 'live-path-mismatch' 'path-mismatch' $true $false 0
Assert-Case 'empty-name-process-still-live' 'live-empty-name' $true $false 0
Assert-Case 'identity-read-error-process-still-live' 'read-error' $true $false 0
Assert-Case 'exit-state-unavailable' 'exit-error' $true $false 0
Assert-Case 'matched-normal-exit-timeout' 'timeout' $true $false 1
Assert-Case 'matched-wait-error-still-live' 'wait-error' $true $false 1
Assert-Case 'matched-instance-exits-during-wait-error' 'wait-exits-error' $false $true 1 'MATCHED_INSTANCE_EXITED'
$a=Wait-HancomOwnedExit -Owner $script:owner -ProcessLookup {param($ProcessId);$null}
if($a.identityError -or $a.exited -ne $true -or $a.waited -or $a.exitObservation -ne 'PID_ABSENT'){throw 'absent PID contract'}
$script:rows+=@{name='PID-already-absent';status='PASS';observed=$a}
$script:lookupCalls=0;$script:fake=New-Fake 'handle-error'
$a=Wait-HancomOwnedExit -Owner $script:owner -ProcessLookup {param($ProcessId);$script:lookupCalls++;if($script:lookupCalls -eq 1){$script:fake}else{$null}}
if($a.identityError -or $a.exited -ne $true -or $a.waited -or $script:lookupCalls -ne 2 -or $a.exitObservation -ne 'PID_ABSENT_BEFORE_HANDLE'){throw 'exit before handle contract'}
$script:rows+=@{name='exit-before-handle-confirmed-fresh-absence';status='PASS';observed=$a;lookups=$script:lookupCalls}
Assert-Case 'handle-error-PID-still-present' 'handle-error' $true $false 0
$a=Wait-HancomOwnedExit -Owner $script:owner -ProcessLookup {throw 'fixture lookup denied'}
if(-not $a.identityError -or $a.exited -eq $true -or $a.waited){throw 'lookup error must block'}
$script:rows+=@{name='lookup-access-denied';status='PASS';observed=$a}
$a=Wait-HancomOwnedExit -Owner ([pscustomobject]@{pid=0;startTicks=0;path=''}) -ProcessLookup {throw 'must not lookup'}
if(-not $a.identityError -or $a.waited){throw 'invalid owner must block'}
$script:rows+=@{name='invalid-owner-no-lookup';status='PASS';observed=$a}
# Execute the original controller block verbatim, with only Get-Process supplied
# by an isolated in-memory fixture. No COM or OS process is started in this test.
$text=[IO.File]::ReadAllText($BaselineController)
$start=$text.IndexOf('    $waitInfo=@{');$end=$text.IndexOf('    $receiptObject.cleanup | Add-Member -NotePropertyName normalExitWait',$start)
if($start -lt 0 -or $end -le $start){throw 'baseline block missing'}
$block=[scriptblock]::Create($text.Substring($start,$end-$start))
function Invoke-OldFixture([string]$Mode) {
    $script:fake=New-Fake $Mode
    function Get-Process {param([int]$Id,$ErrorAction);$script:fake}
    $receiptObject=[pscustomobject]@{cleanup=[pscustomobject]@{quit=$true;owned=$true;owner=$script:owner}}
    . $block
    return $waitInfo
}
$old=Invoke-OldFixture 'exit-empty-name'
if(-not $old.identityError -or $old.identityMatched -ne $false){throw 'original race not reproduced'}
$good=Invoke-OldFixture 'normal'
if($good.identityError -or $good.exited -ne $true){throw 'original valid control failed'}
# Pin the actual helper/controller coupling and unchanged gate predicates via AST.
$candidate=Join-Path $PSScriptRoot 'verify_hwpx_with_hancom.ps1';$current=[IO.File]::ReadAllText($candidate)
foreach($guard in @('if ($receiptObject.cleanup.quit -and $receiptObject.cleanup.owned -and $receiptObject.cleanup.owner)','if ($waitInfo.identityError) { $receiptObject.status=''BLOCKED_COM'' }','if($remaining.Count -gt 0 -or !$receiptObject.cleanup.quit -or !$receiptObject.sourceUnchanged){$receiptObject.status=''BLOCKED_COM''}')) {if(-not $current.Contains($guard)){throw 'controller guard changed'}}
$tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot 'Hancom.OwnedExit.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'helper parse errors'}
$unsafe=$ast.FindAll({param($node)($node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -in @('Stop-Process','Start-Process','Remove-Item','Set-ItemProperty')) -or ($node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and $node.Member.Value -in @('Kill','CloseMainWindow','Refresh'))},$true)
if($unsafe.Count){throw 'helper mutates process or settings'}
$result=@{status='PASS';cases=$script:rows;fixtureCases=$script:rows.Count;baselineRace=@{status='REPRODUCED_BLOCK';observation=$old};baselineValidControl=$good;oldBlockExecutedVerbatim=$true;actualControllerGuardsPreserved=$true;noProcessSignalsOrSettingsWrites=$true;nativeCOMCalls=0;scope='Controlled scheduling fixture establishes repair behavior, not exact historical interleaving.'}
if(Test-Path -LiteralPath $OutputPath){throw 'new output required'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($result|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
Write-Output "PASS $($script:rows.Count) exit/ownership fixtures; original race reproduced; original normal control PASS."

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BaselineHelper,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference='Stop'
$script:owner=[pscustomobject]@{pid=9123;startTicks=639000000000000000;path='C:\Qualified\Hwp.exe'}
$script:rows=@()
function New-Fixture([hashtable]$Flags=@{}) {
    $p=[pscustomobject]@{handleValue=[IntPtr]1;handleThrows=$false;exitFlag=$false;exitThrows=$false;ticks=639000000000000000;nameValue='Hwp';pathValue='C:\Qualified\Hwp.exe';startThrows=$false;nameThrows=$false;pathThrows=$false;nameExits=$false;pathExits=$false;waitResult=$true;waitThrows=$false;waitExits=$false;waitCalls=0;exitReads=0;disposeCalls=0}
    foreach($key in $Flags.Keys){$p.$key=$Flags[$key]}
    $p|Add-Member ScriptProperty Handle {if($this.handleThrows){throw 'fixture handle denied'};$this.handleValue}
    $p|Add-Member ScriptProperty HasExited {$this.exitReads++;if($this.exitThrows){throw 'fixture exit state denied'};[bool]$this.exitFlag}
    $p|Add-Member ScriptProperty StartTime {if($this.startThrows){throw 'fixture start denied'};[datetime]::new($this.ticks,[DateTimeKind]::Utc)}
    $p|Add-Member ScriptProperty ProcessName {if($this.nameExits){$this.exitFlag=$true};if($this.nameThrows){throw 'fixture name denied'};$this.nameValue}
    $p|Add-Member ScriptProperty Path {if($this.pathExits){$this.exitFlag=$true};if($this.pathThrows){throw 'fixture path denied'};$this.pathValue}
    $p|Add-Member ScriptMethod WaitForExit {param($ms);$this.waitCalls++;if($this.waitExits){$this.exitFlag=$true};if($this.waitThrows){throw 'fixture wait denied'};$this.waitResult}
    $p|Add-Member ScriptMethod Dispose {$this.disposeCalls++}
    return $p
}
function Invoke-Observation([object[]]$Sequence,[int]$LimitMs=200) {
    $script:sequence=$Sequence;$script:lookups=0
    $clock=[Diagnostics.Stopwatch]::StartNew()
    $a=Wait-HancomOwnedExit -Owner $script:owner -LimitMs $LimitMs -ProcessLookup {
        param([int]$ProcessId)
        if($ProcessId -ne $script:owner.pid){throw 'unexpected PID'}
        $index=[Math]::Min($script:lookups,$script:sequence.Count-1);$script:lookups++
        $step=$script:sequence[$index]
        if($step -is [string]){throw $step}
        return $step
    }
    return @{observed=$a;lookups=$script:lookups;elapsedMs=$clock.ElapsedMilliseconds}
}
function Assert-Result([string]$Name,$Result,[bool]$Exited,[string]$ErrorPrefix,[int]$Lookups=-1,[string]$Observation='') {
    $a=$Result.observed
    if(($a.exited -eq $true) -ne $Exited){throw "$Name exit contract: $($a|ConvertTo-Json -Compress)"}
    if($ErrorPrefix){if(-not $a.identityError.StartsWith($ErrorPrefix)){throw "$Name expected $ErrorPrefix : $($a|ConvertTo-Json -Compress)"}}
    elseif($a.identityError){throw "$Name unexpected error: $($a.identityError)"}
    if($Lookups -ge 0 -and $Result.lookups -ne $Lookups){throw "$Name lookup count: $($Result.lookups)"}
    if($Observation -and $a.exitObservation -ne $Observation){throw "$Name observation contract"}
    $script:rows+=@{name=$Name;status='PASS';result=$Result}
}
function Assert-Unpinned($Result,[object[]]$Fixtures) {
    if($null -ne $Result.observed.identityMatched -or $Result.observed.waited -or $Result.observed.handleAcquired){throw 'unbound observation claimed ownership/wait/handle'}
    foreach($fixture in $Fixtures){if($fixture.waitCalls -ne 0 -or $fixture.exitReads -ne 0 -or $fixture.disposeCalls -ne 1){throw 'unbound fixture waited, read HasExited, or not disposed exactly once'}}
}

# Reproduce the specific false block against the installed pre-fix implementation.
. $BaselineHelper
$original=New-Fixture @{handleValue=[IntPtr]::Zero}
$baseline=Invoke-Observation @($original,$original,$null)
Assert-Result 'baseline-delayed-PID-absence-reproduces-block' $baseline $false 'HANDLE_UNAVAILABLE_PID_PRESENT' 2
Assert-Unpinned $baseline @($original)

. (Join-Path $PSScriptRoot 'Hancom.OwnedExit.ps1')
$original=New-Fixture @{handleValue=[IntPtr]::Zero}
$result=Invoke-Observation @($original,$original,$null)
Assert-Result 'delayed-PID-absence' $result $true '' 3 'PID_ABSENT_BEFORE_HANDLE'
Assert-Unpinned $result @($original)
if($result.observed.absenceChecks -ne 2){throw 'absenceChecks contract'}

$first=New-Fixture @{handleThrows=$true}
$second=New-Fixture @{handleValue=[IntPtr]::Zero;startThrows=$true;nameThrows=$true;pathThrows=$true}
$third=New-Fixture @{handleValue=[IntPtr]::Zero}
$result=Invoke-Observation @($first,$second,$third,$null)
Assert-Result 'delayed-absence-with-separate-process-wrappers-and-metadata-errors' $result $true '' 4 'PID_ABSENT_BEFORE_HANDLE'
Assert-Unpinned $result @($first,$second,$third)

$original=New-Fixture @{handleValue=[IntPtr]::Zero}
$result=Invoke-Observation @($original,$null) 0
Assert-Result 'immediate-fresh-absence-zero-budget' $result $true '' 2 'PID_ABSENT_BEFORE_HANDLE'
Assert-Unpinned $result @($original)

foreach($case in @(
    @{name='initial-start-mismatch';flags=@{ticks=639000000000000001}},
    @{name='initial-name-mismatch';flags=@{nameValue='OtherApp'}},
    @{name='initial-path-mismatch';flags=@{pathValue='C:\Other\Hwp.exe'}},
    @{name='start-read-error-cannot-hide-name-mismatch';flags=@{startThrows=$true;nameValue='OtherApp'}},
    @{name='start-and-name-errors-cannot-hide-path-mismatch';flags=@{startThrows=$true;nameThrows=$true;pathValue='C:\Other\Hwp.exe'}},
    @{name='known-start-mismatch-cannot-be-erased-by-later-read-errors';flags=@{ticks=639000000000000001;nameThrows=$true;pathThrows=$true}}
)) {
    $case.flags.handleValue=[IntPtr]::Zero
    $original=New-Fixture $case.flags
    $result=Invoke-Observation @($original,$null)
    Assert-Result $case.name $result $false 'OWNERSHIP_MISMATCH' 1
    if($result.observed.identityMatched -ne $false -or $original.waitCalls -or $original.exitReads -or $original.disposeCalls -ne 1){throw 'initial mismatch ownership/dispose contract'}
}
foreach($case in @(
    @{name='reused-PID-start-mismatch';flags=@{ticks=639000000000000001}},
    @{name='fresh-name-mismatch';flags=@{nameValue='OtherApp'}},
    @{name='fresh-path-mismatch';flags=@{pathValue='C:\Other\Hwp.exe'}},
    @{name='fresh-known-mismatch-even-if-already-exited';flags=@{ticks=639000000000000001;exitFlag=$true}},
    @{name='fresh-start-error-path-mismatch';flags=@{startThrows=$true;pathValue='C:\Other\Hwp.exe'}}
)) {
    $original=New-Fixture @{handleValue=[IntPtr]::Zero}
    $fresh=New-Fixture $case.flags
    $result=Invoke-Observation @($original,$fresh,$null)
    Assert-Result $case.name $result $false 'OWNERSHIP_MISMATCH' 2
    if($result.observed.identityMatched -ne $false -or $original.waitCalls -or $fresh.waitCalls -or $fresh.exitReads -or $original.disposeCalls -ne 1 -or $fresh.disposeCalls -ne 1){throw 'fresh mismatch ownership/dispose contract'}
}

foreach($flags in @(@{handleValue=[IntPtr]::Zero},@{handleValue=[IntPtr]::Zero;startThrows=$true;nameThrows=$true;pathThrows=$true})) {
    $original=New-Fixture $flags
    $result=Invoke-Observation @($original) 60
    Assert-Result 'PID-present-until-bounded-timeout' $result $false 'HANDLE_UNAVAILABLE_PID_PRESENT'
    Assert-Unpinned $result @($original)
    if($null -ne $result.observed.exited -or $result.lookups -lt 3 -or $result.elapsedMs -gt 1000){throw 'bounded timeout / unknown state contract'}
}
$original=New-Fixture @{handleValue=[IntPtr]::Zero}
$result=Invoke-Observation @($original) 0
Assert-Result 'PID-present-zero-budget-one-fresh-lookup' $result $false 'HANDLE_UNAVAILABLE_PID_PRESENT' 2
Assert-Unpinned $result @($original)

$original=New-Fixture @{handleValue=[IntPtr]::Zero}
$result=Invoke-Observation @($original,'fixture lookup denied',$null)
Assert-Result 'fresh-lookup-error-does-not-become-absence' $result $false 'fixture lookup denied' 2
Assert-Unpinned $result @($original)
$result=Invoke-Observation @('fixture lookup denied',$null)
Assert-Result 'initial-lookup-error' $result $false 'fixture lookup denied' 1
$result=Invoke-Observation @($null)
Assert-Result 'already-absent' $result $true '' 1 'PID_ABSENT'

# Existing handle-pinned path remains unchanged, including mismatch vetoes.
foreach($case in @(
    @{name='matching-instance-normal-exit';flags=@{};exited=$true;error='';waits=1;observation='MATCHED_INSTANCE_EXITED'},
    @{name='handle-already-exited';flags=@{exitFlag=$true};exited=$true;error='';waits=0;observation='HANDLE_EXITED_BEFORE_IDENTITY'},
    @{name='exit-during-name-read';flags=@{nameExits=$true;nameValue=''};exited=$true;error='';waits=0;observation='HANDLE_EXITED_DURING_IDENTITY'},
    @{name='live-start-mismatch';flags=@{ticks=639000000000000001};exited=$false;error='OWNERSHIP_MISMATCH';waits=0},
    @{name='live-name-mismatch';flags=@{nameValue='OtherApp'};exited=$false;error='OWNERSHIP_MISMATCH';waits=0},
    @{name='live-path-mismatch';flags=@{pathValue='C:\Other\Hwp.exe'};exited=$false;error='OWNERSHIP_MISMATCH';waits=0},
    @{name='known-name-mismatch-even-if-exits';flags=@{nameExits=$true;nameValue='OtherApp'};exited=$false;error='OWNERSHIP_MISMATCH';waits=0},
    @{name='live-unknown-name';flags=@{nameValue=''};exited=$false;error='IDENTITY_UNAVAILABLE_PROCESS_LIVE';waits=0},
    @{name='unknown-exit-state';flags=@{exitThrows=$true};exited=$false;error='EXIT_STATE_UNAVAILABLE';waits=0},
    @{name='matched-exit-timeout';flags=@{waitResult=$false};exited=$false;error='OWNED_EXIT_TIMEOUT';waits=1},
    @{name='matched-wait-error';flags=@{waitThrows=$true};exited=$false;error='Exception calling "WaitForExit"';waits=1},
    @{name='matched-exit-during-wait-error';flags=@{waitThrows=$true;waitExits=$true};exited=$true;error='';waits=1;observation='MATCHED_INSTANCE_EXITED'}
)) {
    $original=New-Fixture $case.flags
    $result=Invoke-Observation @($original)
    Assert-Result $case.name $result $case.exited $case.error 1 $case.observation
    if($original.waitCalls -ne $case.waits -or $original.disposeCalls -ne 1){throw "$($case.name) wait/dispose contract"}
}
$a=Wait-HancomOwnedExit -Owner ([pscustomobject]@{pid=0;startTicks=0;path=''}) -ProcessLookup {throw 'must not lookup'}
if(-not $a.identityError.StartsWith('INVALID_OWNER') -or $a.exited -eq $true -or $a.waited){throw 'invalid owner contract'}
$script:rows+=@{name='invalid-owner';status='PASS';observed=$a}

$candidate=Join-Path $PSScriptRoot 'Hancom.OwnedExit.ps1'
$tokens=$null;$parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($candidate,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw 'helper parse errors'}
$unsafe=$ast.FindAll({param($node)($node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -in @('Stop-Process','Start-Process','Wait-Process','Remove-Item','Set-ItemProperty')) -or ($node -is [Management.Automation.Language.InvokeMemberExpressionAst] -and $node.Member.Value -in @('Kill','CloseMainWindow','Refresh'))},$true)
if($unsafe.Count){throw 'unexpected process/settings operation'}
$result=@{status='PASS';caseCount=$script:rows.Count;cases=$script:rows;baselineHelperSha256=(Get-FileHash -LiteralPath $BaselineHelper -Algorithm SHA256).Hash;candidateHelperSha256=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash;powerShellVersion=$PSVersionTable.PSVersion.ToString();nativeCOMCalls=0;osProcessStarts=0;scope='Deterministic lookup/metadata fixtures; does not establish a specific native interleaving or native post-fix success.'}
if(Test-Path -LiteralPath $OutputPath){throw 'new output required'}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),($result|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
Write-Output "PASS $($script:rows.Count) ownership/exit fixtures; old race reproduced; no COM/process starts."

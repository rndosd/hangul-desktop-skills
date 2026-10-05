# Read-only post-Quit observation. This helper never signals or terminates a process.
function Wait-HancomOwnedExit {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)]$Owner,
        [ValidateRange(0,10000)][int]$LimitMs=10000,
        [scriptblock]$ProcessLookup={param([int]$ProcessId) Get-Process -Id $ProcessId -ErrorAction Stop}
    )
    $info=@{limitMs=$LimitMs;identityMatched=$null;waited=$false;exited=$null;identityError=$null;handleAcquired=$false;exitObservation=$null;identityReadError=$null}
    $active=$null
    try {
        if ([long]$Owner.pid -le 0 -or [long]$Owner.pid -gt [int]::MaxValue -or [long]$Owner.startTicks -le 0 -or [string]::IsNullOrWhiteSpace($Owner.path)) {
            throw 'INVALID_OWNER: positive PID/startTicks and recorded executable path required.'
        }
        try { $active=& $ProcessLookup ([int]$Owner.pid) }
        catch {
            if ($_.FullyQualifiedErrorId -like 'NoProcessFoundForGivenId,*') {$active=$null}
            else {throw}
        }
        if ($null -eq $active) {$info.exited=$true;$info.exitObservation='PID_ABSENT';return $info}
        try {
            # Pin this instance before reading process metadata; PID is not an instance ID.
            $handle=$active.Handle
            if ($null -eq $handle -or $handle -eq [IntPtr]::Zero) {throw 'No process handle available.'}
            $info.handleAcquired=$true
        } catch {
            $info.identityReadError=$_.Exception.Message
            # If exit preceded handle acquisition, confirm absence with one fresh lookup.
            # A present/reused PID or lookup error remains blocked; do not wait on it.
            $fresh=$null
            try {$fresh=& $ProcessLookup ([int]$Owner.pid)}
            catch {if ($_.FullyQualifiedErrorId -notlike 'NoProcessFoundForGivenId,*') {throw}}
            if ($null -eq $fresh) {$info.exited=$true;$info.exitObservation='PID_ABSENT_BEFORE_HANDLE';return $info}
            if ($fresh -ne $active) {$fresh.Dispose()}
            throw 'HANDLE_UNAVAILABLE_PID_PRESENT: no wait or termination performed.'
        }
        $state=$active.HasExited
        if ($state -isnot [bool]) {throw 'EXIT_STATE_UNAVAILABLE'}
        if ($state) {$info.exited=$true;$info.exitObservation='HANDLE_EXITED_BEFORE_IDENTITY';return $info}
        $knownMismatch=$false;$complete=$false
        try {
            $ticks=$active.StartTime.ToUniversalTime().Ticks
            if ($ticks -ne [long]$Owner.startTicks) {$knownMismatch=$true}
            $name=$active.ProcessName
            if (-not [string]::IsNullOrWhiteSpace($name) -and $name -ne 'Hwp') {$knownMismatch=$true}
            $path=$active.Path
            if (-not [string]::IsNullOrWhiteSpace($path) -and $path -ine [string]$Owner.path) {$knownMismatch=$true}
            $complete=(-not [string]::IsNullOrWhiteSpace($name) -and -not [string]::IsNullOrWhiteSpace($path))
        } catch {$info.identityReadError=$_.Exception.Message}
        if ($knownMismatch) {
            $info.identityMatched=$false
            throw 'OWNERSHIP_MISMATCH: no wait or termination performed.'
        }
        if (-not $complete -or $info.identityReadError) {
            $state=$active.HasExited
            if ($state -isnot [bool]) {throw 'EXIT_STATE_UNAVAILABLE'}
            if ($state) {$info.exited=$true;$info.exitObservation='HANDLE_EXITED_DURING_IDENTITY';return $info}
            throw 'IDENTITY_UNAVAILABLE_PROCESS_LIVE: no wait or termination performed.'
        }
        $info.identityMatched=$true;$info.waited=$true
        try {$info.exited=$active.WaitForExit($LimitMs)}
        catch {
            $info.identityReadError=$_.Exception.Message
            $state=$active.HasExited
            if ($state -isnot [bool] -or -not $state) {throw}
            $info.exited=$true
        }
        if ($info.exited -ne $true) {throw 'OWNED_EXIT_TIMEOUT: no termination performed.'}
        $info.exitObservation='MATCHED_INSTANCE_EXITED'
    } catch {$info.identityError=$_.Exception.Message}
    finally {if ($null -ne $active) {$active.Dispose()}}
    return $info
}

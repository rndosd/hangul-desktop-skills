param([Parameter(Mandatory)][string]$JobPath,[Parameter(Mandatory)][string]$RunDirectory)
. (Join-Path $PSScriptRoot 'Hancom.Cell.Common.ps1')
. (Join-Path $PSScriptRoot 'Hancom.Environment.ps1')
$job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
$script:EventPath=Join-Path $RunDirectory 'events.jsonl'
$script:Stage='initialize'; $hwp=$null; $owned=$false
$r=[ordered]@{status='FAIL_COM';stage=$null;failure=$null;firstOpen=$false;saveAs=$false;reopen=$false;pdfExport=$false;mutation=$null;cleanup=@{quit=$false};visual='NOT_REVIEWED'}
try {
    if($job.operation -in @('SetAlignmentMany','SetAlignmentGrid') -and ((Get-Sha256 $job.input) -ine $job.sourceSha256 -or !$job.output -or !$job.pdf)){throw 'INPUT_INVALID: multi-table source binding or outputs'}
    if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -ne 0){throw 'PROCESS_CONFLICT: Hangul already running'}
    $securityModuleName=Assert-HancomSecurityBinding (Get-HancomEnvironment)
    $birth=[DateTime]::UtcNow
    $hwp=Invoke-HancomCall 'com.create' {New-Object -ComObject HWPFrame.HwpObject}
    # Link the actual COM window to its OS process, never infer ownership from a PID difference.
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class HancomWindowPid { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); }'
    $window=$hwp.XHwpWindows.Item(0)
    $hwnd=[IntPtr]([long]$window.WindowHandle)
    [uint32]$serverId=0
    $null=[HancomWindowPid]::GetWindowThreadProcessId($hwnd,[ref]$serverId)
    $server=Get-Process -Id $serverId
    if($server.ProcessName -ne 'Hwp' -or $server.StartTime.ToUniversalTime() -lt $birth.AddSeconds(-1)){throw 'OWNERSHIP_UNPROVEN: window PID or creation time'}
    $identity=@{pid=$server.Id;startTicks=$server.StartTime.ToUniversalTime().Ticks;path=$server.Path;hwnd=$hwnd.ToInt64()}
    Write-NewJson $identity (Join-Path $RunDirectory 'owner.json');$owned=$true
    $r.version=[string]$hwp.Version
    $window.Visible=$false
    $null=Invoke-HancomCall 'security.register' {$hwp.RegisterModule('FilePathCheckDLL',[string]$securityModuleName)} -RequireTrue
    if($job.operation -eq 'Probe'){$r.status='PASS_COM_PROBE'}else{
        $null=Invoke-HancomCall 'document.open' {$hwp.Open([string]$job.input,'','')} -RequireTrue
        $r.firstOpen=$true;$r.pagesBefore=[int]$hwp.PageCount
        $action=$hwp.HAction
        Select-VerifiedFirstCell $hwp $action $job
        if($job.operation -in @('InspectGrid','SetAlignmentGrid')){$r.grid=Read-GridTarget $hwp $action $job}
        $r.selection=@{runtimeId=$script:VerifiedTableId;text=$job.targetText;parentText=$job.parentText}
        if($job.operation -in @('SetAlignment','SetAlignmentMany','SetAlignmentGrid')){$r.mutation=Set-CellAlignment $hwp $action $job}
        if($job.output){
            if(Test-Path -LiteralPath $job.output){throw 'OUTPUT_EXISTS: refusing overwrite'}
            $null=Invoke-HancomCall 'document.saveAs' {$hwp.SaveAs([string]$job.output,'HWPX','')} -RequireTrue
            if(!(Test-Path -LiteralPath $job.output)){throw 'OUTPUT_MISSING: SaveAs'}
            $r.saveAs=$true
            $null=Invoke-HancomCall 'document.clear' {$hwp.Clear(1)}
            $null=Invoke-HancomCall 'document.reopen' {$hwp.Open([string]$job.output,'','')} -RequireTrue
            $r.reopen=$true;$r.pagesAfter=[int]$hwp.PageCount
            if($null -ne $r.mutation){
                Select-VerifiedFirstCell $hwp $action $job
                if($job.operation -eq 'SetAlignmentGrid'){$r.gridReopened=Read-GridTarget $hwp $action $job}
                $read=Read-CellAlignment $hwp $action
                foreach($key in $r.mutation.wanted.Keys){if($read.values[$key] -ne $r.mutation.wanted[$key]){throw "READBACK_MISMATCH: $key after reopen"}}
                $r.mutation.reopened=$read.values
            }
        }
        if($job.pdf){
            if(Test-Path -LiteralPath $job.pdf){throw 'OUTPUT_EXISTS: refusing PDF overwrite'}
            $null=Invoke-HancomCall 'document.pdf' {$hwp.SaveAs([string]$job.pdf,'PDF','')} -RequireTrue
            $r.pdfExport=(Test-Path -LiteralPath $job.pdf)
            if(!$r.pdfExport){throw 'OUTPUT_MISSING: PDF'}
        }
        $r.status='PASS_COM'
    }
}catch{$r.stage=$script:Stage;$r.failure=Get-FailureCode $_.Exception;Write-Event $script:Stage 'FAILED' $r.failure}
finally {
    # Never Quit an object that could be attached to a preexisting user instance.
    if($null -ne $hwp -and $owned){
        try{$null=Invoke-HancomCall 'cleanup.clear' {$hwp.Clear(1)}}catch{Write-Event 'cleanup.clear' 'FAILED'}
        try{$null=Invoke-HancomCall 'cleanup.quit' {$hwp.Quit()};$r.cleanup.quit=$true}catch{Write-Event 'cleanup.quit' 'FAILED'}
    }
    if($null -ne $hwp){try{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp)}catch{}}
    Write-NewJson $r (Join-Path $RunDirectory 'worker-receipt.json')
}
if($r.status -notlike 'PASS_COM*'){exit 3}

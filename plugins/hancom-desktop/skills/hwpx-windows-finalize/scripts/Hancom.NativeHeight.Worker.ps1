param([Parameter(Mandatory)][string]$JobPath,[Parameter(Mandatory)][string]$RunDirectory)
. (Join-Path $PSScriptRoot 'Hancom.RowSplit.Common.ps1')
. (Join-Path $PSScriptRoot 'Hancom.Environment.ps1')
$job=Get-Content -LiteralPath $JobPath -Raw -Encoding UTF8 | ConvertFrom-Json
$script:EventPath=Join-Path $RunDirectory 'events.jsonl'
$script:Stage='initialize'; $hwp=$null; $owned=$false
$r=[ordered]@{status='FAIL_COM';stage=$null;failure=$null;firstOpen=$false;saveAs=$false;reopen=$false;pdfExport=$false;mutation=$null;cleanup=@{quit=$false};visual='NOT_REVIEWED';comCreated=$false;securityModuleRegistered=$false;registerModuleArguments=$null}
try {
    if($job.operation -ne 'InspectGrid' -or $job.output -or $job.pdf){throw 'INPUT_INVALID: height readback worker only InspectGrid without outputs'}
    if($job.operation -in @('SetAlignmentMany','SetAlignmentGrid') -and ((Get-Sha256 $job.input) -ine $job.sourceSha256 -or !$job.output -or !$job.pdf)){throw 'INPUT_INVALID: multi-table source binding or outputs'}
    if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -ne 0){throw 'PROCESS_CONFLICT: Hangul already running'}
    $securityModuleName=Assert-HancomSecurityBinding (Get-HancomEnvironment)
    $birth=[DateTime]::UtcNow
    $hwp=Invoke-HancomCall 'com.create' {New-Object -ComObject HWPFrame.HwpObject}
    $r.comCreated=$true
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
    if(($r.version -replace '\s','') -ne '13,0,0,3903'){throw 'UNVERIFIED_BUILD: measured table geometry qualified only on13.0.0.3903'}
    $window.Visible=$false
    $null=Invoke-HancomCall 'security.register' {$hwp.RegisterModule('FilePathCheckDLL',[string]$securityModuleName)} -RequireTrue
    $r.securityModuleRegistered=$true;$r.registerModuleArguments=@('FilePathCheckDLL',[string]$securityModuleName)
    if($job.operation -eq 'Probe'){$r.status='PASS_COM_PROBE'}else{
        $null=Invoke-HancomCall 'document.open' {$hwp.Open([string]$job.input,'','')} -RequireTrue
        $r.firstOpen=$true;$r.pagesBefore=[int]$hwp.PageCount
        $action=$hwp.HAction
        Select-VerifiedFirstCell $hwp $action $job
        if($job.operation -in @('InspectGrid','SetAlignmentGrid','SplitRowGroup')){$r.grid=Read-GridTarget $hwp $action $job}

function Read-TableGeometryValues($h,[string]$Context){
    $rows=@()
    foreach($method in @('dynamic-action-set','typed-HShapeObject')){
        $values=@();$returned=$null;$errorMessage=$null
        try{
            if($method -eq 'dynamic-action-set'){
                $a=$h.CreateAction('TablePropertyDialog');$s=$a.CreateSet()
                $returned=Invoke-HancomCall ('height.'+$Context+'.dynamic.GetDefault') {$a.GetDefault($s)}
            }else{
                $shape=$h.HParameterSet.HShapeObject;$s=$shape.HSet
                $returned=Invoke-HancomCall ('height.'+$Context+'.typed.GetDefault') {$h.HAction.GetDefault('TablePropertyDialog',$s)}
            }
            foreach($key in @('Width','Height','LayoutWidth','LayoutHeight','PageNumber','OutsideMarginTop','OutsideMarginBottom')){
                try{
                    if($method -eq 'dynamic-action-set'){$exists=$s.ItemExist($key);$raw=if($exists){$s.Item($key)}else{$null}}
                    else{$exists=$null;$raw=$shape.$key}
                    $valid=($null -ne $raw -and $raw -is [ValueType] -and $raw -isnot [bool])
                    $values+=@{name=$key;exists=$exists;raw=$raw;type=$(if($null -ne $raw){$raw.GetType().FullName}else{$null});numeric=$valid;status=$(if($valid){'READ_NUMERIC'}else{'UNVERIFIED_ABSENT_OR_NONNUMERIC'})}
                }catch{$values+=@{name=$key;status='PROPERTY_UNAVAILABLE';error=$_.Exception.Message}}
            }
        }catch{$errorMessage=$_.Exception.Message}
        $rows+=@{method=$method;context=$Context;getDefaultReturned=$returned;values=$values;error=$errorMessage;noExecuteOrSetItem=$true}
    }
    return $rows
}
if($job.operation -ne 'InspectGrid' -or $job.output -or $job.pdf){throw 'INPUT_INVALID: height readback is read-only'}
$p=$hwp.ParentCtrl
if($null -eq $p -or $p.CtrlID -ne 'tbl' -or [string]$p.GetCtrlInstID() -ne $script:VerifiedTableId){throw 'SELECTION_MISMATCH: measured caret parent'}
$r.tableGeometry=@{tableId=$script:VerifiedTableId;caretPosition=(Read-CellPosition ($hwp.GetPosBySet()));caret=(Read-TableGeometryValues $hwp 'verified-last-cell');selected=$null}
$selectedReturn=Invoke-HancomCall 'height.selectExactTable' {$hwp.SelectCtrl($script:VerifiedTableId,1)}
$ctrl=$hwp.CurSelectedCtrl
if($null -eq $ctrl -or $ctrl.CtrlID -ne 'tbl' -or [string]$ctrl.GetCtrlInstID() -ne $script:VerifiedTableId){throw 'SELECTION_MISMATCH: measured selected table'}
Assert-SelectCtrlResult $selectedReturn ([string]$hwp.Version)
$r.tableGeometry.selected=Read-TableGeometryValues $hwp 'verified-selected-table'

        $r.selection=@{runtimeId=$script:VerifiedTableId;text=$job.targetText;parentText=$job.parentText}
        if($job.operation -in @('SetAlignment','SetAlignmentMany','SetAlignmentGrid')){$r.mutation=Set-CellAlignment $hwp $action $job}
        if($job.operation -eq 'SplitRowGroup'){
            $r.mutation=@{action='TableSplitTable';selectedRow=$job.gridPlan.ownerCell.row;expectedCellText=$job.gridPlan.ownerCell.text;sourceTableId=$script:VerifiedTableId}
            $null=Invoke-HancomCall 'table.splitAtVerifiedRow' {$action.Run('TableSplitTable')} -RequireTrue
            $tables=@();$ctrl=$hwp.HeadCtrl;$visited=0
            while($null -ne $ctrl){if(++$visited -gt 200){throw 'SELECTION_MISMATCH: post-split traversal bound'};if($ctrl.CtrlID -eq 'tbl'){$tables+=,[string]$ctrl.GetCtrlInstID()};$ctrl=$ctrl.Next}
            if($tables.Count -ne 2 -or $tables[0] -eq $tables[1]){throw 'READBACK_MISMATCH: split did not make two distinct tables'}
            $r.mutation.tableIds=$tables
        }
        if($job.output){
            if(Test-Path -LiteralPath $job.output){throw 'OUTPUT_EXISTS: refusing overwrite'}
            $null=Invoke-HancomCall 'document.saveAs' {$hwp.SaveAs([string]$job.output,'HWPX','')} -RequireTrue
            if(!(Test-Path -LiteralPath $job.output)){throw 'OUTPUT_MISSING: SaveAs'}
            $r.saveAs=$true
            $null=Invoke-HancomCall 'document.clear' {$hwp.Clear(1)}
            $null=Invoke-HancomCall 'document.reopen' {$hwp.Open([string]$job.output,'','')} -RequireTrue
            $r.reopen=$true;$r.pagesAfter=[int]$hwp.PageCount
            if($null -ne $r.mutation -and $job.operation -ne 'SplitRowGroup'){
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

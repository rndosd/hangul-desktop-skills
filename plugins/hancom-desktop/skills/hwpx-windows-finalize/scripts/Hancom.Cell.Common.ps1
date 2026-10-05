<#
Implementation version: 1.0.0 (2026-09-08). Independent PowerShell implementation.
Selection sequence informed by read-only pyhwpx core.py get_into_nth_table:
https://github.com/martiniifun/pyhwpx/commit/a83b782673ecf49e18964610edea1d12c23b7f09
Commit label Release v1.7.2. No pyhwpx import/install, ROT attach, cache deletion,
or registry/security configuration changes. Upstream MIT notice retained below.
Official desktop selection: https://forum.developer.hancom.com/t/topic/2114
Control identity: https://forum.developer.hancom.com/t/topic/2713
Official ActionTable_2504 ParagraphShape / ParameterSetTable AlignType:
0 JUSTIFY, 2 RIGHT. Only these values are exposed by this bounded implementation.
E01/E02 verified on installed Hancom; receipt records actual Hwp.Version.
Copyright (C) 2012 Yoshimasa Niwa

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#>
# Tested, narrow desktop Hancom operations. No registry or XML writes.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-Sha256([string]$Path) {
    $stream=[IO.File]::OpenRead($Path);$algorithm=[Security.Cryptography.SHA256]::Create()
    try{return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','')}
    finally{$stream.Dispose();$algorithm.Dispose()}
}
function Write-NewJson($Value, [string]$Path) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Depth 18))
    $stream = [IO.File]::Open($Path, 'CreateNew', 'Write', 'None')
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}
function Write-Event([string]$Stage, [string]$State, $Data = $null) {
    $event = [ordered]@{utc=[DateTime]::UtcNow.ToString('o');stage=$Stage;state=$State;data=$Data}
    [IO.File]::AppendAllText($script:EventPath, (($event | ConvertTo-Json -Depth 12 -Compress) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
}
function Invoke-HancomCall([string]$Stage, [scriptblock]$Call, [switch]$RequireTrue) {
    $script:Stage = $Stage
    Write-Event $Stage 'BEGIN'
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $value = & $Call
    if ($RequireTrue -and $value -ne $true) { throw "RETURN_FALSE: $Stage" }
    Write-Event $Stage 'END' @{elapsedMs=$watch.ElapsedMilliseconds}
    return $value
}
function Get-FailureCode($Exception) {
    $e=$Exception
    while($null -ne $e.InnerException){$e=$e.InnerException}
    $hex='0x' + $e.HResult.ToString('X8')
    $code=switch($hex){
        '0x80010105' {'RPC_E_SERVERFAULT'}
        '0x80010108' {'RPC_E_DISCONNECTED'}
        '0x80010001' {'RPC_E_CALL_REJECTED'}
        '0x8001010A' {'RPC_E_SERVERCALL_RETRYLATER'}
        '0x8001010B' {'RPC_E_SERVERCALL_REJECTED'}
        '0x80010007' {'RPC_E_SERVER_DIED'}
        '0x80010012' {'RPC_E_SERVER_DIED_DNE'}
        '0x8001010E' {'RPC_E_WRONG_THREAD'}
        '0x8001010F' {'RPC_E_THREAD_NOT_INIT'}
        '0x80030020' {'STG_E_SHAREVIOLATION'}
        '0x80030021' {'STG_E_LOCKVIOLATION'}
        '0x80030070' {'STG_E_MEDIUMFULL'}
        '0x80040154' {'REGDB_E_CLASSNOTREG'}
        default {if($Exception.Message -match '^([A-Z_]+):'){$Matches[1]}else{'CALL_FAILED'}}
    }
    return @{code=$code;hresult=$hex;message=$Exception.Message}
}
function Assert-SelectCtrlResult($Returned,[string]$Version){
    if($Returned -eq $true){return}
    if($null -ne $Returned -and $Returned -eq $false -and ($Version -replace '\s','') -eq '13,0,0,653'){return}
    throw 'RETURN_FALSE: SelectCtrl requires true outside verified build 13.0.0.653'
}
function Read-CellPosition($s){
    if($null -eq $s){throw 'POSITION_INVALID: null parameter set'}
    $values=@{};$rawLog=@{}
    foreach($key in @('List','Para','Pos')){
        if(!$s.ItemExist($key)){throw "POSITION_INVALID: missing $key"}
        $raw=$s.Item($key)
        if($null -eq $raw){throw "POSITION_INVALID: null $key"}
        $rawLog[$key]=@{value=$raw;type=$raw.GetType().FullName}
        if($raw -isnot [ValueType] -or $raw -is [bool]){throw "POSITION_INVALID: nonnumeric $key"}
        [int]$parsed=0
        if(![int]::TryParse([string]$raw,[ref]$parsed) -or $parsed -lt 0){throw "POSITION_INVALID: invalid integer $key"}
        $values[$key.ToLowerInvariant()]=$parsed
    }
    Write-Event 'position.raw' 'CHECKED' $rawLog
    return $values
}
function Select-VerifiedFirstCell($h,$action,$job){
    $many=($job.operation -in @('InspectMany','SetAlignmentMany','InspectGrid','SetAlignmentGrid'))
    if($job.operation -eq 'InspectMany' -and ($job.output -or $job.pdf)){throw 'INPUT_INVALID: InspectMany cannot save'}
    $tables=@();$c=$h.HeadCtrl;$visited=0
    while($null -ne $c){
        if(++$visited -gt $(if($many){500}else{100})){throw 'SELECTION_MISMATCH: traversal limit'}
        if($c.CtrlID -eq 'tbl'){$tables+=,$c}
        $c=$c.Next
    }
    $expectedCount=if($job.parentText){2}else{1};$isSimple=($expectedCount -eq 1)
    if($job.operation -in @('InspectGrid','SetAlignmentGrid')){
        if($tables.Count -ne $job.gridPlan.tableCount){throw 'SELECTION_MISMATCH: grid table count'}
        $tables=@($tables[[int]$job.gridPlan.tableOrdinal-1])
        if([string]$tables[0].GetCtrlInstID() -cne [string]$job.gridPlan.tableId){throw 'SELECTION_MISMATCH: grid table identity'}
    }elseif($many){
        if($tables.Count -ne [int]$job.expectedTableCount){throw 'SELECTION_MISMATCH: full table count'}
        $tables=@($tables[[int]$job.parentOrdinal-1],$tables[[int]$job.targetOrdinal-1])
        Write-Event 'tables.candidateSubset' 'READ_ONLY' @{fullCount=$job.expectedTableCount;parentOrdinal=$job.parentOrdinal;targetOrdinal=$job.targetOrdinal}
    }
    if($tables.Count -ne $expectedCount){throw "SELECTION_MISMATCH: table count $($tables.Count)"}
    $ids=@($tables|ForEach-Object{[string]$_.GetCtrlInstID()})
    if(!$ids[0] -or (!$isSimple -and (!$ids[1] -or $ids[0] -eq $ids[1]))){throw 'SELECTION_MISMATCH: unique runtime IDs'}
    Write-Event 'tables' 'CHECKED' @{count=$expectedCount;runtimeIds=$ids;visited=$visited}
    $observations=@()
    foreach($table in $tables){
        $id=[string]$table.GetCtrlInstID()
        $immediate=Read-CellPosition ($table.GetAnchorPos(0));$root=Read-CellPosition ($table.GetAnchorPos(2))
        $returned=Invoke-HancomCall 'table.select' {$h.SelectCtrl($id,1)}
        $selected=$h.CurSelectedCtrl
        $selectedId=if($null -ne $selected){[string]$selected.GetCtrlInstID()}else{$null}
        Write-Event 'table.selection' 'READ' @{requestedId=$id;returned=$returned;selectedId=$selectedId;immediateAnchor=$immediate;rootAnchor=$root}
        if($null -eq $selected -or $selected.CtrlID -ne 'tbl' -or $selectedId -ne $id){throw 'SELECTION_MISMATCH: selected ID'}
        Assert-SelectCtrlResult $returned ([string]$h.Version)
        # The established build-specific SelectCtrl false return is accepted only with exact ID readback.
        $null=Invoke-HancomCall 'cell.first' {$action.Run('ShapeObjTableSelCell')} -RequireTrue
        $parent=$h.ParentCtrl
        if($null -eq $parent -or $parent.CtrlID -ne 'tbl' -or [string]$parent.GetCtrlInstID() -ne $id){throw 'SELECTION_MISMATCH: first cell parent'}
        $prePosition=Read-CellPosition ($h.GetPosBySet())
        $preMode=$h.SelectionMode
        if($null -eq $preMode){throw 'SELECTION_MISMATCH: null selection mode'}
        $preCtrl=$h.CurSelectedCtrl;$preId=if($null -ne $preCtrl){[string]$preCtrl.GetCtrlInstID()}else{$null}
        Write-Event 'cancel.before' 'READ' @{position=$prePosition;selectionMode=$preMode;maskedMode=([int]$preMode -band 15);parentId=[string]$parent.GetCtrlInstID();selectedId=$preId}
        $null=Invoke-HancomCall 'cell.cancelBlockOnce' {$action.Run('Cancel')} -RequireTrue
        $postPosition=Read-CellPosition ($h.GetPosBySet());$postMode=$h.SelectionMode
        $parent=$h.ParentCtrl;$postCtrl=$h.CurSelectedCtrl;$postId=if($null -ne $postCtrl){[string]$postCtrl.GetCtrlInstID()}else{$null}
        $postParentId=if($null -ne $parent){[string]$parent.GetCtrlInstID()}else{$null}
        Write-Event 'cancel.after' 'READ' @{position=$postPosition;selectionMode=$postMode;maskedMode=([int]$postMode -band 15);parentId=$postParentId;selectedId=$postId}
        if($null -eq $postMode -or ([int]$postMode -band 15) -ne 0 -or $postParentId -ne $id -or $null -ne $postCtrl){throw 'SELECTION_MISMATCH: post-Cancel caret context'}
        foreach($key in @('list','para','pos')){if($prePosition[$key] -ne $postPosition[$key]){throw 'SELECTION_MISMATCH: Cancel coordinate shift'}}
        $initial=Read-CellPosition ($h.GetPosBySet())
        Write-Event 'cell.parent' 'CHECKED' @{parentId=[string]$parent.GetCtrlInstID();position=$initial}
        if($null -ne $h.CurSelectedCtrl){throw 'SELECTION_MISMATCH: object selection remains before text'}
        $startSet=$h.GetPosBySet();$start=Read-CellPosition $startSet
        foreach($key in @('list','para','pos')){if($initial[$key] -ne $start[$key]){throw 'POSITION_MISMATCH: fresh reads differ'}}
        if($start.para -ne 0 -or $start.pos -ne 0){throw 'POSITION_MISMATCH: first paragraph start unconfirmed'}
        $parent=$h.ParentCtrl
        if($null -eq $parent -or $parent.CtrlID -ne 'tbl' -or [string]$parent.GetCtrlInstID() -ne $id -or $null -ne $h.CurSelectedCtrl){throw 'SELECTION_MISMATCH: start context'}
        Write-Event 'cell.startVerifiedWithoutMove' 'CHECKED' @{initial=$initial;fresh=$start;parentId=$id}
        $null=Invoke-HancomCall 'cell.selectParaEnd' {$action.Run('MoveSelParaEnd')} -RequireTrue
        $end=Read-CellPosition ($h.GetPosBySet())
        Write-Event 'cell.textRange' 'READ' @{start=$start;end=$end}
        if($start.list -ne $initial.list -or $end.list -ne $start.list -or $end.para -ne $start.para -or $end.pos -le $start.pos){throw 'SELECTION_MISMATCH: paragraph range'}
        $parent=$h.ParentCtrl
        if($null -eq $parent -or [string]$parent.GetCtrlInstID() -ne $id){throw 'SELECTION_MISMATCH: selected text parent'}
        $text=[string](Invoke-HancomCall 'cell.readText' {$h.GetTextFile('TEXT','saveblock')})
        $label=$text.Trim()
        Write-Event 'cell.text' 'READ' @{id=$id;text=$label}

        $null=Invoke-HancomCall 'cell.cancelTextSelection' {$action.Run('Cancel')} -RequireTrue
        $null=Invoke-HancomCall 'cell.restore' {$h.SetPosBySet($startSet)} -RequireTrue
        $restored=Read-CellPosition ($h.GetPosBySet())
        foreach($key in @('list','para','pos')){if($restored[$key] -ne $start[$key]){throw 'SELECTION_MISMATCH: cell restore readback'}}
        $parent=$h.ParentCtrl
        if($null -eq $parent -or [string]$parent.GetCtrlInstID() -ne $id){throw 'SELECTION_MISMATCH: restored parent'}
        $observations+=@{savedSet=$startSet;runtimeId=$id;label=$label;firstCell=$start;immediateAnchor=$immediate;rootAnchor=$root;restored=$restored}
    }
    $target=@($observations|Where-Object{$_.label -ceq $job.targetText})
    if($target.Count -ne 1){throw 'SELECTION_MISMATCH: target text must match exactly one first paragraph'}
    if(!$isSimple){
        $outer=@($observations|Where-Object{$_.label -ceq $job.parentText})
        if($outer.Count -ne 1 -or $outer[0].runtimeId -eq $target[0].runtimeId -or $target[0].immediateAnchor.list -ne $outer[0].firstCell.list -or $target[0].firstCell.list -eq $outer[0].firstCell.list){throw 'SELECTION_MISMATCH: nested parent ownership'}
    }
    $null=Invoke-HancomCall 'target.restore' {$h.SetPosBySet($target[0].savedSet)} -RequireTrue
    $script:VerifiedTableId=[string]$target[0].runtimeId
    $position=Read-CellPosition ($h.GetPosBySet())
    foreach($key in @('list','para','pos')){if($position[$key] -ne $target[0].firstCell[$key]){throw 'SELECTION_MISMATCH: final target coordinates'}}
    $null=Read-CellAlignment $h $action
    Write-Event 'target.verified' 'CHECKED' @{runtimeId=$script:VerifiedTableId;text=$target[0].label;position=$position}
}

function Read-CellAlignment($h,$action){
    $p=$h.ParentCtrl;$position=Read-CellPosition ($h.GetPosBySet())
    if($null -eq $p -or $p.CtrlID -ne 'tbl' -or $null -ne $h.CurSelectedCtrl -or ($null -eq $h.SelectionMode -or ([int]$h.SelectionMode -band 15) -ne 0) -or $position.para -ne 0 -or $position.pos -ne 0){throw 'SELECTION_MISMATCH: E02 caret context'}
    if([string]$p.GetCtrlInstID() -ne $script:VerifiedTableId){throw 'SELECTION_MISMATCH: not verified inner ID'}
    # Selection restored the uniquely matched first paragraph, independent of control order.
    $parameters=$h.HParameterSet;$para=$parameters.HParaShape;$set=$para.HSet
    $null=Invoke-HancomCall 'paragraph.getDefault' {$action.GetDefault('ParagraphShape',$set)} -RequireTrue
    $raw=$para.AlignType
    if($null -eq $raw){throw 'PROPERTY_UNCONFIRMED: AlignType null'}
    $values=@{alignType=[int]$raw}
    Write-Event 'paragraph.context' 'READ' @{parentId=[string]$p.GetCtrlInstID();position=$position;values=$values}
    return @{parameters=$parameters;para=$para;set=$set;values=$values;parentId=[string]$p.GetCtrlInstID();position=$position}
}
function Assert-GridParagraphRange($Start,$End,[bool]$ExpectedEmpty){
    if($End.list -ne $Start.list -or $End.para -ne $Start.para -or $End.pos -lt $Start.pos){throw 'SELECTION_MISMATCH: grid text range'}
    $zero=($End.pos -eq $Start.pos)
    if($zero -ne $ExpectedEmpty){throw 'SELECTION_MISMATCH: empty paragraph evidence mismatch'}
    return $zero
}

function Read-GridTarget($h,$action,$job){
    if($job.operation -notin @('InspectGrid','SetAlignmentGrid') -or ($job.operation -eq 'InspectGrid' -and ($job.output -or $job.pdf))){throw 'INPUT_INVALID: grid reading context'}
    $plan=$job.gridPlan
    if($plan.actions.Count -gt 20 -or $plan.route.Count -ne $plan.actions.Count+1){throw 'INPUT_INVALID: grid route limit'}
    $observed=@();$seen=@{}
    for($i=0;$i -le $plan.actions.Count;$i++){
        if($i -gt 0){
            $move=[string]$plan.actions[$i-1]
            if($move -notin @('TableRightCell','TableLowerCell')){throw 'INPUT_INVALID: unsupported grid movement'}
            $null=Invoke-HancomCall 'grid.moveCell' {$action.Run($move)} -RequireTrue
        }
        $set=$h.GetPosBySet();$start=Read-CellPosition $set
        $parent=$h.ParentCtrl
        if($null -eq $parent -or [string]$parent.GetCtrlInstID() -ne $script:VerifiedTableId -or $start.para -ne 0 -or $start.pos -ne 0 -or ([int]$h.SelectionMode -band 15) -ne 0){throw 'SELECTION_MISMATCH: grid cell context'}
        if($seen.ContainsKey($start.list)){throw 'SELECTION_MISMATCH: grid movement repeated cell'}
        $seen[$start.list]=$true
        $null=Invoke-HancomCall 'grid.selectParagraph' {$action.Run('MoveSelParaEnd')} -RequireTrue
        $end=Read-CellPosition ($h.GetPosBySet())
        $empty=Assert-GridParagraphRange $start $end ([bool]$plan.route[$i].emptyFirstParagraph)
        # Never call saveblock without a nonempty selection: it may read beyond
        # the intended empty paragraph. Zero range is checked against the package.
        $text=if($empty){''}else{([string]$h.GetTextFile('TEXT','saveblock')).Trim()}
        $null=Invoke-HancomCall 'grid.cancel' {$action.Run('Cancel')} -RequireTrue
        $null=Invoke-HancomCall 'grid.restore' {$h.SetPosBySet($set)} -RequireTrue
        $restored=Read-CellPosition ($h.GetPosBySet())
        foreach($key in @('list','para','pos')){if($restored[$key] -ne $start[$key]){throw 'SELECTION_MISMATCH: grid restore'}}
        $restoredParentId=[string]$h.ParentCtrl.GetCtrlInstID()
        Write-Event 'grid.routeReadback' 'CHECKED' @{index=$i;action=$(if($i -gt 0){$plan.actions[$i-1]}else{'anchor'});position=$start;expectedRow=$plan.route[$i].row;expectedColumn=$plan.route[$i].column;textMatches=($text -ceq $plan.route[$i].text);parentMatches=($restoredParentId -eq $script:VerifiedTableId)}
        if($restoredParentId -ne $script:VerifiedTableId -or $text -cne $plan.route[$i].text){throw 'SELECTION_MISMATCH: grid route text or parent'}
        $observed+=@{index=$i;position=$start;endPosition=$end;text=$text;row=$plan.route[$i].row;column=$plan.route[$i].column;emptyFirstParagraphVerified=$empty;paragraphCount=$plan.route[$i].paragraphCount}
    }
    return @{requested=$plan.requested;ownerCell=$plan.ownerCell;tableId=$script:VerifiedTableId;observations=$observed;scope='read_only_no_mutation'}
}

function Set-CellAlignment($h,$action,$job){
    $ctx=Read-CellAlignment $h $action
    if($ctx.values.alignType -ne [int]$job.expected){throw 'DEFAULT_MISMATCH: source alignment differs from expected'}
    $want=[int]$job.alignment
    $ctx.para.AlignType=$want
    Write-Event 'paragraph.request' 'PREPARED' @{parentId=$ctx.parentId;before=$ctx.values.alignType;wanted=$want}
    $null=Invoke-HancomCall 'paragraph.execute' {$action.Execute('ParagraphShape',$ctx.set)} -RequireTrue
    $read=Read-CellAlignment $h $action
    if($read.parentId -ne $ctx.parentId -or $read.values.alignType -ne $want){throw 'READBACK_MISMATCH: E02 immediate'}
    return @{before=$ctx.values;wanted=@{alignType=$want};immediate=$read.values;targetParentId=$ctx.parentId}
}


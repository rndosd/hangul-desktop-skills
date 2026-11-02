# Steps of a resolved hwpx.native-assemble.v1 plan (native_assembly.py). Runs inside the owned
# composition worker; ownership, security module, save/reopen/PDF and cleanup stay in hancom_worker.ps1.
function Move-HancomBodyEnd($Hwp) {
    if($Hwp.SetPos(0,0,0) -eq $false -or $Hwp.HAction.Run('MoveDocEnd') -eq $false) { throw 'BODY_END_NAVIGATION_FAILED' }
    if([int]$Hwp.GetPosBySet().Item('List') -ne 0) { throw 'ASSEMBLY_REQUIRES_ROOT_BODY_END' }
}

function Get-HancomSelectionText($Hwp) {
    # Hangul returns some symbols as &#NNNNN; references.
    return [Net.WebUtility]::HtmlDecode([string]$Hwp.GetTextFile('TEXT','saveblock')).Trim()
}

function Set-HancomPlaceholderText($Hwp,[string]$Find,[string]$Text) {
    # The newest copy of a placeholder is the part inserted last, so search backward from the end.
    # AllReplace reports false even after replacing; the selected text is checked instead.
    [void]$Hwp.HAction.Run('MoveDocEnd')
    $search=$Hwp.HParameterSet.HFindReplace
    [void]$Hwp.HAction.GetDefault('RepeatFind',$search.HSet)
    $search.FindString=$Find;$search.IgnoreMessage=1;$search.FindRegExp=0;$search.Direction=$Hwp.FindDir('Backward')
    [void]$Hwp.HAction.Execute('RepeatFind',$search.HSet)
    if((Get-HancomSelectionText $Hwp) -ne $Find) { throw "ASSEMBLY_PLACEHOLDER_NOT_FOUND: $Find" }
    if($Text -eq '') { [void]$Hwp.HAction.Run('Delete'); return }
    $insert=$Hwp.HParameterSet.HInsertText
    [void]$Hwp.HAction.GetDefault('InsertText',$insert.HSet);$insert.Text=$Text
    if($Hwp.HAction.Execute('InsertText',$insert.HSet) -eq $false) { throw 'ASSEMBLY_TEXT_FAILED' }
}

function Get-HancomLastControl($Hwp,[string]$Id) {
    $last=$null;$control=$Hwp.HeadCtrl
    while($control) { if($control.CtrlID -eq $Id){$last=$control};$control=$control.Next }
    if(!$last) { throw "ASSEMBLY_CONTROL_NOT_FOUND: $Id" }
    return $last
}

function Enter-HancomLastTable($Hwp) {
    $table=Get-HancomLastControl $Hwp 'tbl'
    [void]$Hwp.SetPosBySet($table.GetAnchorPos(0));[void]$Hwp.FindCtrl()
    [void]$Hwp.HAction.Run('ShapeObjTableSelCell');[void]$Hwp.HAction.Run('Cancel')
}

function Set-HancomTableRows($Hwp,$Step) {
    $have=[int]$Step.have;$rows=@($Step.rows);$need=$rows.Count;$columns=[int]$Step.cols
    Enter-HancomLastTable $Hwp
    if($need -lt $have) {
        for($i=0;$i -le $need;$i++){[void]$Hwp.HAction.Run('TableLowerCell')}
        for($i=0;$i -lt $have-$need;$i++){if($Hwp.HAction.Run('TableDeleteRow') -eq $false){throw 'ASSEMBLY_ROW_DELETE_FAILED'}}
    } elseif($need -gt $have) {
        for($i=0;$i -lt $have;$i++){[void]$Hwp.HAction.Run('TableLowerCell')}
        for($i=0;$i -lt $need-$have;$i++){if($Hwp.HAction.Run('TableAppendRow') -eq $false){throw 'ASSEMBLY_ROW_APPEND_FAILED'}}
    }
    Enter-HancomLastTable $Hwp
    foreach($row in $rows) {
        [void]$Hwp.HAction.Run('TableLowerCell');[void]$Hwp.HAction.Run('TableColBegin')
        for($column=0;$column -lt $columns;$column++) {
            $value=[string]@($row)[$column]
            if($column -eq 0 -and $value -ne ''){$value=[string]$Step.prefix+$value}
            [void]$Hwp.HAction.Run('MoveListBegin');[void]$Hwp.HAction.Run('MoveSelListEnd')
            if($value -eq '') { [void]$Hwp.HAction.Run('Delete') }  # an empty insert would keep the old text
            else {
                $insert=$Hwp.HParameterSet.HInsertText
                [void]$Hwp.HAction.GetDefault('InsertText',$insert.HSet);$insert.Text=$value
                [void]$Hwp.HAction.Execute('InsertText',$insert.HSet)
            }
            if($column -lt $columns-1){[void]$Hwp.HAction.Run('TableRightCell')}
        }
    }
    [void]$Hwp.HAction.Run('Cancel')
    return @{have=$have;rows=$need;cols=$columns}
}

function Invoke-HancomAssembly($Hwp,$Plan,$Report) {
    $parts=@{};foreach($property in $Plan.parts.PSObject.Properties){$parts[$property.Name]=$property.Value}
    $Report.assembly=@{steps=0;texts=0;tables=@();boxes=@();pageNumbers=$null}
    $index=0
    foreach($step in $Plan.steps) {
        Write-HancomStage "assemble-$index-$($step.op)"
        switch($step.op) {
            'text' { Set-HancomPlaceholderText $Hwp ([string]$step.find) ([string]$step.text);$Report.assembly.texts++ }
            'section' { Move-HancomBodyEnd $Hwp;if($Hwp.HAction.Run('BreakSection') -eq $false){throw 'ASSEMBLY_BREAK_FAILED'} }
            'insert' {
                Move-HancomBodyEnd $Hwp
                $position=$Hwp.GetPosBySet();$part=$parts[[string]$step.part]
                $parameters=$Hwp.HParameterSet.HInsertFile
                [void]$Hwp.HAction.GetDefault('InsertFile',$parameters.HSet)
                $parameters.filename=$part.path;$parameters.KeepSection=[int]$step.keepSection
                $parameters.KeepCharshape=1;$parameters.KeepParashape=1;$parameters.KeepStyle=1
                if($Hwp.HAction.Execute('InsertFile',$parameters.HSet) -eq $false) { throw "INSERT_FILE_FAILED: $($step.part)" }
                $Report.inserted+=@{part=$step.part;path=$part.path;sha256=$part.sha256;keepSection=[int]$step.keepSection;position=@{list=0;para=[int]$position.Item('Para');offset=[int]$position.Item('Pos')}}
            }
            'pageNumbers' {
                $numbers=$Hwp.HParameterSet.HPageNumPos
                [void]$Hwp.HAction.GetDefault('PageNumPos',$numbers.HSet)
                $numbers.DrawPos=$Hwp.PageNumPosition([string]$step.position);$numbers.NumberFormat=$Hwp.NumberFormat([string]$step.format)
                $numbers.SideChar=[int][char][string]$step.sideChar
                $Report.assembly.pageNumbers=[bool]$Hwp.HAction.Execute('PageNumPos',$numbers.HSet)
                if(!$Report.assembly.pageNumbers) { throw 'ASSEMBLY_PAGE_NUMBERS_FAILED' }
            }
            'boxWidth' {
                $box=Get-HancomLastControl $Hwp 'gso'
                # A fresh set changes only the width; writing back the group's own Properties turns its fills black.
                $size=$Hwp.CreateSet('ShapeObject');$size.SetItem('Width',[int]$step.width);$box.Properties=$size
                $actual=[int]$box.Properties.Item('Width')
                if([Math]::Abs($actual-[int]$step.width) -gt 2) { throw "ASSEMBLY_BOX_WIDTH_FAILED: $actual" }
                $Report.assembly.boxes+=@{requested=[int]$step.width;actual=$actual}
            }
            'table' { $Report.assembly.tables+=(Set-HancomTableRows $Hwp $step) }
            default { throw "ASSEMBLY_UNKNOWN_STEP: $($step.op)" }
        }
        $Report.assembly.steps++
        $index++
    }
}

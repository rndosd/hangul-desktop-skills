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
    # Text typed over a selection takes the format of the character before it, which at a paragraph
    # start is the previous paragraph's. Typing after the placeholder's first character keeps its own
    # format; the placeholder characters around the new text are then deleted.
    $start=$Hwp.CreateSet('ListParaPos');$end=$Hwp.CreateSet('ListParaPos')
    if(!$Hwp.GetSelectedPosBySet($start,$end)) { throw "ASSEMBLY_PLACEHOLDER_NOT_FOUND: $Find" }
    $list=[int]$start.Item('List');$para=[int]$start.Item('Para');$pos=[int]$start.Item('Pos')
    [void]$Hwp.HAction.Run('Cancel')
    if(!$Hwp.SetPos($list,$para,$pos+1)) { throw 'ASSEMBLY_TEXT_FAILED' }
    $insert=$Hwp.HParameterSet.HInsertText
    [void]$Hwp.HAction.GetDefault('InsertText',$insert.HSet);$insert.Text=$Text
    if($Hwp.HAction.Execute('InsertText',$insert.HSet) -eq $false) { throw 'ASSEMBLY_TEXT_FAILED' }
    # Rest of the placeholder, then its first character. One character at a time: deleting a selection
    # that ends before a control (a cover's page-number hiding) deletes the control too.
    $after=[int]$Hwp.GetPosBySet().Item('Pos')
    foreach($range in @(@($after,($Find.Length-1)),@($pos,1))) {
        if(!$Hwp.SetPos($list,$para,$range[0])) { throw 'ASSEMBLY_TEXT_FAILED' }
        for($i=0;$i -lt $range[1];$i++) { if($Hwp.HAction.Run('Delete') -eq $false) { throw 'ASSEMBLY_TEXT_FAILED' } }
    }
}

function Get-HancomLastControl($Hwp,[string]$Id) {
    $last=$null;$control=$Hwp.HeadCtrl
    while($control) { if($control.CtrlID -eq $Id){$last=$control};$control=$control.Next }
    if(!$last) { throw "ASSEMBLY_CONTROL_NOT_FOUND: $Id" }
    return $last
}

function Get-HancomLastLine($Hwp,[int]$Para) {
    # (start of the paragraph's last line, end of the paragraph) as character positions; start 0 is one line
    if(!$Hwp.SetPos(0,$Para,0) -or [int]$Hwp.GetPosBySet().Item('Para') -ne $Para) { return $null }
    [void]$Hwp.HAction.Run('MoveParaEnd');$end=[int]$Hwp.GetPosBySet().Item('Pos')
    [void]$Hwp.HAction.Run('MoveLineBegin');$start=[int]$Hwp.GetPosBySet().Item('Pos')
    return @($start,$end)
}

function Set-HancomParagraphSpacing($Hwp,[int]$Para,[string]$Action,[int]$Times) {
    for($i=0;$i -lt $Times;$i++) {
        [void]$Hwp.SetPos(0,$Para,0);[void]$Hwp.HAction.Run('MoveSelParaEnd')
        $done=$Hwp.HAction.Run($Action);[void]$Hwp.HAction.Run('Cancel')
        if($done -eq $false) { throw "ASSEMBLY_SPACING_FAILED: $Action" }
    }
}

function Invoke-HancomFitShortLines($Hwp,[int]$MaxSteps,[int]$TailChars) {
    # What authors do by hand: a body paragraph whose last line is short (TailChars, or the share of the earlier
    # characters MaxSteps 1% steps can take back) gets its letters squeezed one step at a time until that line is
    # gone; past MaxSteps it goes back as it was.
    $fitted=0;$kept=0
    Move-HancomBodyEnd $Hwp;$last=[int]$Hwp.GetPosBySet().Item('Para')  # SetPos past the end lands on the last paragraph
    for($para=0;$para -le $last;$para++) {
        $line=Get-HancomLastLine $Hwp $para
        if($null -eq $line) { continue }
        $tail=$line[1]-$line[0]
        # MaxSteps 1% steps take back about that share of the characters before the last line
        if($line[0] -gt 0 -and $tail -gt 0 -and $tail -le [Math]::Max($TailChars,[int]($line[0]*$MaxSteps/100))) {
            $steps=0
            while($steps -lt $MaxSteps) {
                Set-HancomParagraphSpacing $Hwp $para 'CharShapeSpacingDecrease' 1;$steps++
                $now=Get-HancomLastLine $Hwp $para
                if($now[0] -lt $line[0]) { break }  # the last line moved up: one line fewer
            }
            if($now[0] -lt $line[0]) { $fitted++ } else { Set-HancomParagraphSpacing $Hwp $para 'CharShapeSpacingIncrease' $steps;$kept++ }
        }
    }
    return @{fitted=$fitted;unchanged=$kept;paragraphs=$last+1}
}

function Invoke-HancomAssembly($Hwp,$Plan,$Report) {
    $parts=@{};foreach($property in $Plan.parts.PSObject.Properties){$parts[$property.Name]=$property.Value}
    $Report.assembly=@{steps=0;texts=0;boxes=@();pageNumbers=$null}
    $index=0
    foreach($step in $Plan.steps) {
        Write-HancomStage "assemble-$index-$($step.op)"
        switch($step.op) {
            'text' { Set-HancomPlaceholderText $Hwp ([string]$step.find) ([string]$step.text);$Report.assembly.texts++ }
            'section' { Move-HancomBodyEnd $Hwp;if($Hwp.HAction.Run('BreakSection') -eq $false){throw 'ASSEMBLY_BREAK_FAILED'} }
            'pageBreak' { Move-HancomBodyEnd $Hwp;if($Hwp.HAction.Run('BreakPage') -eq $false){throw 'ASSEMBLY_PAGE_BREAK_FAILED'} }
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
            'fitShortLines' { $Report.assembly.fitShortLines=Invoke-HancomFitShortLines $Hwp ([int]$step.maxSteps) ([int]$step.tailChars) }
            'trimEnd' {
                # The last part's empty trailer paragraph ends the body; on a full last page it starts an empty page.
                Move-HancomBodyEnd $Hwp
                $position=$Hwp.GetPosBySet()
                if([int]$position.Item('Pos') -eq 0 -and [int]$position.Item('Para') -gt 0) {
                    if($Hwp.HAction.Run('DeleteBack') -eq $false) { throw 'ASSEMBLY_TRIM_FAILED' }
                }
            }
            default { throw "ASSEMBLY_UNKNOWN_STEP: $($step.op)" }
        }
        $Report.assembly.steps++
        $index++
    }
}

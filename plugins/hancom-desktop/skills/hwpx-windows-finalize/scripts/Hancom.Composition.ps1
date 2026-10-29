# Official append actions only. Ownership, security, save/reopen and cleanup
# remain in hancom_worker.ps1. Input hashes are read before Open and after Quit.
function Read-HancomComposition([string]$PlanPath,[string]$PlanSha256,[string]$Candidate,[string]$SourceSha256) {
    if ((Get-FinalizeSha256 $PlanPath) -ine $PlanSha256) { throw 'COMPOSITION_PLAN_CHANGED' }
    $plan=Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($plan.schema -ne 'hwpx.native-compose.v1' -or @($plan.blocks).Count -lt 1 -or @($plan.blocks).Count -gt 20) { throw 'INVALID_COMPOSITION_PLAN' }
    if ([IO.Path]::GetFullPath($plan.base.path) -ine $Candidate) { throw 'COMPOSITION_BASE_MISMATCH' }
    $hashes=@{};$hashes[$Candidate]=$SourceSha256
    foreach($inputRef in @($plan.base)+@($plan.blocks)) {
        if(!$hashes.ContainsKey($inputRef.path)){$hashes[$inputRef.path]=Get-FinalizeSha256 $inputRef.path}
        if ([IO.Path]::GetExtension($inputRef.path) -ine '.hwpx' -or $hashes[$inputRef.path] -ine $inputRef.sha256) { throw 'COMPOSITION_INPUT_CHANGED' }
    }
    foreach($block in $plan.blocks) { if($block.join -notin @('none','paragraph','page','section')) { throw 'INVALID_COMPOSITION_JOIN' } }
    return $plan
}

function Invoke-HancomComposition($Hwp,$Plan,$Report) {
    $index=0
    foreach($block in $Plan.blocks) {
        Write-HancomStage "compose-$index-start"
        if($Hwp.SetPos(0,0,0) -eq $false -or $Hwp.HAction.Run('MoveDocEnd') -eq $false) { throw 'BODY_END_NAVIGATION_FAILED' }
        $position=$Hwp.GetPosBySet()
        if([int]$position.Item('List') -ne 0) { throw 'COMPOSITION_REQUIRES_ROOT_BODY_END' }
        $action=@{paragraph='BreakPara';page='BreakPage';section='BreakSection'}[$block.join]
        if($action -and $Hwp.HAction.Run($action) -eq $false) { throw 'COMPOSITION_BREAK_FAILED' }
        $position=$Hwp.GetPosBySet()
        if([int]$position.Item('List') -ne 0) { throw 'COMPOSITION_LEFT_ROOT_BODY' }
        $parameters=$Hwp.HParameterSet.HInsertFile
        [void]$Hwp.HAction.GetDefault('InsertFile',$parameters.HSet)
        $parameters.filename=$block.path
        $parameters.KeepSection=if($block.join -eq 'section'){1}else{0}
        $parameters.KeepCharshape=1
        $parameters.KeepParashape=1
        $parameters.KeepStyle=1
        if($Hwp.HAction.Execute('InsertFile',$parameters.HSet) -eq $false) { throw 'INSERT_FILE_FAILED' }
        $Report.inserted+=@{path=$block.path;sha256=$block.sha256;join=$block.join;keepSection=$parameters.KeepSection;position=@{list=0;para=[int]$position.Item('Para');offset=[int]$position.Item('Pos')}}
        Write-HancomStage "compose-$index-done"
        $index++
    }
}

function Test-HancomCompositionInputs($Plan,[string]$Candidate,[string]$SourceSha256) {
    $checks=@();$hashes=@{};$hashes[$Candidate]=$SourceSha256
    foreach($inputRef in @($Plan.base)+@($Plan.blocks)) {
        $actual=$null;$errorText=$null
        try {
            if(!$hashes.ContainsKey($inputRef.path)){$hashes[$inputRef.path]=Get-FinalizeSha256 $inputRef.path}
            $actual=$hashes[$inputRef.path]
        } catch {$errorText=$_.Exception.Message}
        $checks+=@{path=$inputRef.path;expected=$inputRef.sha256;actual=$actual;unchanged=($actual -ieq $inputRef.sha256);error=$errorText}
    }
    return $checks
}

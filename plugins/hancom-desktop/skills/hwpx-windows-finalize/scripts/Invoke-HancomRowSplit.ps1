[CmdletBinding()]
param(
 [Parameter(Mandatory)][ValidateSet('InspectGrid','SplitRowGroup')][string]$Operation,
 [string]$InputPath,[string]$OutputPath,[string]$PdfPath,
 [ValidateSet(0,2,3)][Nullable[int]]$Expected,
 [ValidateSet(0,2)][Nullable[int]]$Alignment,
 [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$TargetText,
 [string]$ParentText,
 [int]$ExpectedTableCount=0,[int]$TargetOrdinal=0,[int]$ParentOrdinal=0,
 [string]$ExpectedSourceSha256,
 [string]$GridPlanPath,
 [Parameter(Mandatory)][string]$RunDirectory,
 [ValidateRange(5,300)][int]$TimeoutSeconds=45
)
. (Join-Path $PSScriptRoot 'Hancom.RowSplit.Common.ps1')
$run=[IO.Path]::GetFullPath($RunDirectory)
if(Test-Path -LiteralPath $run){throw 'RunDirectory must be new; prior receipts are immutable.'}
$null=New-Item -ItemType Directory -Path $run
$r=[ordered]@{schema=1;implementationVersion='1.0.0';status='FAIL_PREFLIGHT';operation=$Operation;failure=$null;worker=$null;cleanup=$null;sourceUnchanged=$null;artifacts=@();visual='NOT_REVIEWED';structuralPreservation='NOT_CHECKED';nonTargetPreservation='NOT_CHECKED';startedUtc=[DateTime]::UtcNow.ToString('o')}
$mutex=$null;$locked=$false;$proc=$null;$source=$null;$hashBefore=$null
try{
    if($Operation -eq 'SetAlignmentGrid'){throw 'UNVERIFIED_OPERATION: grid alignment save/reopen routing failed; write disabled pending independent read-only diagnosis'}
    $mutex=[Threading.Mutex]::new($false,'Local\CodexHancomAutomation')
    try{$locked=$mutex.WaitOne(0)}catch [Threading.AbandonedMutexException]{$locked=$true}
    if(!$locked){throw 'LOCK_CONFLICT: another common runner owns COM'}
    if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -gt 0){throw 'PROCESS_CONFLICT: existing Hangul process; no COM call issued'}
    if($Operation -ne 'Probe'){
        $source=(Resolve-Path -LiteralPath $InputPath).Path
        if([IO.Path]::GetExtension($source) -ine '.hwpx'){throw 'INPUT_INVALID: expected HWPX'}
        $hashBefore=Get-Sha256 $source
    }
    $dest=if($OutputPath){[IO.Path]::GetFullPath($OutputPath)}else{$null}
    $pdf=if($PdfPath){[IO.Path]::GetFullPath($PdfPath)}else{$null}
    $gridPlan=$null
    if($Operation -in @('InspectGrid','SetAlignmentGrid','SplitRowGroup')){
        if(!$GridPlanPath -or ($Operation -eq 'InspectGrid' -and ($dest -or $pdf -or $null -ne $Alignment))){throw 'INPUT_INVALID: grid plan or read-only outputs'}
        $gridPlan=Get-Content -LiteralPath $GridPlanPath -Raw -Encoding UTF8|ConvertFrom-Json
        if($gridPlan.schema -ne 'hwpx.grid-cell-plan.v3' -or $gridPlan.source.sha256 -ine $hashBefore -or [IO.Path]::GetFullPath($gridPlan.source.path) -ine $source -or $TargetText -cne $gridPlan.route[0].text -or $ParentText){throw 'INPUT_INVALID: grid plan source or first cell mismatch'}
        if($Operation -eq 'SetAlignmentGrid' -and (!$gridPlan.ownerCell.text -or !$gridPlan.ownerCell.plainFirstParagraph -or $gridPlan.ownerCell.paragraphCount -ne 1 -or $gridPlan.ownerCell.rowSpan -ne 1 -or $gridPlan.ownerCell.columnSpan -ne 1)){throw 'INPUT_INVALID: grid write requires nonempty single-paragraph unmerged target cell'}
    }
    if($Operation -eq 'SplitRowGroup'){
        $qualifiedPath=Join-Path $PSScriptRoot 'row-selection-qualification.json'
        if(!(Test-Path -LiteralPath $qualifiedPath)){throw 'UNVERIFIED_BUILD: complete read-only qualification first'}
        $qualified=Get-Content -LiteralPath $qualifiedPath -Raw -Encoding UTF8|ConvertFrom-Json
        if($qualified.status -ne 'PASS_READ_ONLY_QUALIFICATION' -or $qualified.actualVersion -ne '13, 0, 0, 3903' -or $qualified.positiveCount -ne 2 -or $qualified.negativeCount -ne 1 -or (Get-Sha256 (Join-Path $PSScriptRoot 'Hancom.RowSplit.Common.ps1')) -ine $qualified.common.sha256 -or (Get-Sha256 (Join-Path $PSScriptRoot 'Hancom.RowSplit.Worker.ps1')) -ine $qualified.worker.sha256){throw 'UNVERIFIED_BUILD: qualification binding mismatch'}
        foreach($proof in $qualified.receipts){if((Get-Sha256 $proof.path) -ine $proof.sha256){throw 'UNVERIFIED_BUILD: changed qualification receipt'}}
    }
    if($Operation -eq 'SplitRowGroup' -and (!$dest -or !$pdf -or $ExpectedSourceSha256 -ine $hashBefore -or $gridPlan.tableCount -ne 1 -or $gridPlan.ownerCell.row -lt 2 -or $gridPlan.ownerCell.column -ne 1 -or $null -ne $Alignment -or $null -ne $Expected)){throw 'INPUT_INVALID: row split needs exact hash, one table, first-column nonfirst row and new outputs'}
    if($TargetText -cne $TargetText.Trim() -or ($ParentText -and ($ParentText -cne $ParentText.Trim() -or $ParentText -ceq $TargetText))){throw 'INPUT_INVALID: use distinct trimmed first-paragraph text'}
    if($Operation -in @('SetAlignment','SetAlignmentMany','SetAlignmentGrid') -and (!$dest -or $null -eq $Expected -or $null -eq $Alignment)){throw 'INPUT_INVALID: OutputPath, Expected and Alignment required'}
    if($Operation -eq 'SetAlignment' -and $Expected -eq 3){throw 'INPUT_INVALID: legacy alignment range remains 0/2'}
    if($Operation -in @('SetAlignmentMany','SetAlignmentGrid') -and (!$pdf -or $ExpectedSourceSha256 -notmatch '^[a-fA-F0-9]{64}$' -or $hashBefore -ine $ExpectedSourceSha256)){throw 'INPUT_INVALID: multi-table write requires matching source hash and PDF output'}
    if($Operation -in @('SetAlignmentMany','SetAlignmentGrid') -and ($Expected -ne 3 -or $Alignment -ne 2)){throw 'INPUT_INVALID: multi-table write currently supports only verified 3 to 2'}
    if($Operation -in @('Inspect','InspectMany') -and ($dest -or $pdf -or $null -ne $Alignment)){throw 'INPUT_INVALID: Inspect produces receipts only'}
    if($Operation -in @('InspectMany','SetAlignmentMany')){
        if($ExpectedTableCount -lt 3 -or $ExpectedTableCount -gt 100 -or $TargetOrdinal -lt 1 -or $TargetOrdinal -gt $ExpectedTableCount -or $ParentOrdinal -lt 1 -or $ParentOrdinal -gt $ExpectedTableCount -or $ParentOrdinal -eq $TargetOrdinal -or !$ParentText){throw 'INPUT_INVALID: bounded distinct target/parent ordinals and count required'}
    }elseif($ExpectedTableCount -or $TargetOrdinal -or $ParentOrdinal){throw 'INPUT_INVALID: multi-table selectors require a Many operation'}
    # The worker calls Hwp.RegisterModule before opening the document. A registry
    # read here is not authoritative under Codex MSIX registry virtualization.
    if($dest -and [IO.Path]::GetExtension($dest) -ine '.hwpx'){throw 'INPUT_INVALID: output extension'}
    if($pdf -and [IO.Path]::GetExtension($pdf) -ine '.pdf'){throw 'INPUT_INVALID: PDF extension'}
    foreach($path in @($dest,$pdf)){
        if(!$path){continue}
        if($path -eq $source -or (Test-Path -LiteralPath $path)){throw 'OUTPUT_EXISTS: source/output must never be overwritten'}
        if(!(Test-Path -LiteralPath (Split-Path $path -Parent) -PathType Container)){throw 'INPUT_INVALID: output parent missing'}
    }
    $job=@{operation=$Operation;input=$source;output=$dest;pdf=$pdf;expected=$Expected;alignment=$Alignment;targetText=$TargetText;parentText=$ParentText;expectedTableCount=$ExpectedTableCount;targetOrdinal=$TargetOrdinal;parentOrdinal=$ParentOrdinal;sourceSha256=$hashBefore;gridPlan=$gridPlan}
    $jobPath=Join-Path $run 'job.json';Write-NewJson $job $jobPath
    $worker=Join-Path $PSScriptRoot 'Hancom.RowSplit.Worker.ps1'
    foreach($arg in @($worker,$jobPath,$run)){if($arg.Contains('"')){throw 'INPUT_INVALID: quote in path'}}
    $args='-NoProfile -STA -File "'+$worker+'" -JobPath "'+$jobPath+'" -RunDirectory "'+$run+'"'
    $proc=Start-Process -FilePath "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'stdout.log') -RedirectStandardError (Join-Path $run 'stderr.log')
    if(!$proc.WaitForExit($TimeoutSeconds*1000)){
        $proc.Kill();$proc.WaitForExit()
        $r.status='TIMEOUT';$r.failure=@{code='WORKER_TIMEOUT';seconds=$TimeoutSeconds;writeOutcome='UNKNOWN_CHECK_ARTIFACTS_BEFORE_RETRY'}
    }else{
        $wr=Join-Path $run 'worker-receipt.json'
        if(Test-Path -LiteralPath $wr){$r.worker=Get-Content -LiteralPath $wr -Raw -Encoding UTF8|ConvertFrom-Json;$r.status=$r.worker.status;$r.failure=$r.worker.failure}
        else{$r.status='WORKER_CRASH';$r.failure=@{code='NO_WORKER_RECEIPT';exitCode=$proc.ExitCode}}
    }
}catch{$r.failure=Get-FailureCode $_.Exception}
finally{
    $ownerPath=Join-Path $run 'owner.json'
    $cleanup=@{ownership='NOT_RECORDED';forced=$false;remaining=@()}
    if(Test-Path -LiteralPath $ownerPath){
        $owner=Get-Content -LiteralPath $ownerPath -Raw -Encoding UTF8|ConvertFrom-Json
        $cleanup.ownership='COM_HWND_PID_STARTTIME_PATH'
        $p=Get-Process -Id $owner.pid -ErrorAction SilentlyContinue
        if($null -ne $p){
            if($p.ProcessName -eq 'Hwp' -and $p.StartTime.ToUniversalTime().Ticks -eq $owner.startTicks -and $p.Path -eq $owner.path){
                if(!$p.WaitForExit(2000)){$p.Kill();$cleanup.forced=$true;$null=$p.WaitForExit(3000)}
            }else{$cleanup.ownership='IDENTITY_CHANGED_NO_KILL'}
        }
    }
    $cleanup.remaining=@(Get-Process Hwp -ErrorAction SilentlyContinue|ForEach-Object{$_.Id})
    $r.cleanup=$cleanup
    if($source -and $hashBefore){$r.sourceUnchanged=((Get-Sha256 $source) -eq $hashBefore)}
    foreach($name in @('OutputPath','PdfPath')){
        $path=Get-Variable -Name $name -ValueOnly
        if($path -and (Test-Path -LiteralPath $path -PathType Leaf)){$r.artifacts+=@{path=[IO.Path]::GetFullPath($path);sha256=(Get-Sha256 $path);bytes=(Get-Item -LiteralPath $path).Length}}
    }
    if($r.status -like 'PASS_COM*' -and ($cleanup.remaining.Count -gt 0 -or $r.sourceUnchanged -eq $false)){$r.status='FAIL_POSTCONDITION'}
    $r.finishedUtc=[DateTime]::UtcNow.ToString('o')
    Write-NewJson $r (Join-Path $run 'receipt.json')
    if($locked){$mutex.ReleaseMutex()};if($mutex){$mutex.Dispose()}
}
$r | ConvertTo-Json -Depth 18
if($r.status -notlike 'PASS_COM*'){exit 3}

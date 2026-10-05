[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$SimpleFixture,
 [Parameter(Mandatory)][string]$NestedFixture,
 [Parameter(Mandatory)][string]$ResultsDirectory
)
# Explicit real-COM regression test. Fixtures: E01 simple / E02 nested labels.
# Each case runs serially through the same exclusive parent as production.
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($ResultsDirectory)
if(Test-Path -LiteralPath $root){throw 'ResultsDirectory must be new'}
$null=New-Item -ItemType Directory -Path $root
$exe="$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$entry=Join-Path $PSScriptRoot 'Invoke-HancomCell.ps1'
$cases=@(
 @{name='simple';input=$SimpleFixture;target='T06 R1C1';parent='';op='Inspect';expectedExit=0},
 @{name='wrong_target';input=$NestedFixture;target='NO_SUCH_TARGET';parent='OUTER_R1C1_HOST';op='SetAlignment';alignment=2;expectedExit=3},
 @{name='wrong_parent';input=$NestedFixture;target='INNER_R1C1';parent='NO_SUCH_PARENT';op='SetAlignment';alignment=2;expectedExit=3},
 @{name='baseline';input=$NestedFixture;target='INNER_R1C1';parent='OUTER_R1C1_HOST';op='SetAlignment';alignment=0;expectedExit=0},
 @{name='right';input=$NestedFixture;target='INNER_R1C1';parent='OUTER_R1C1_HOST';op='SetAlignment';alignment=2;expectedExit=0}
)
$results=@()
foreach($case in $cases){
 $run=Join-Path $root $case.name
 $args=@('-NoProfile','-File',$entry,'-Operation',$case.op,'-InputPath',$case.input,'-TargetText',$case.target,'-RunDirectory',$run)
 if($case.parent){$args+=@('-ParentText',$case.parent)}
 $out=Join-Path $root ($case.name+'.hwpx')
 if($case.op -eq 'SetAlignment'){$args+=@('-Expected','0','-Alignment',[string]$case.alignment,'-OutputPath',$out,'-PdfPath',(Join-Path $root ($case.name+'.pdf')))}
 & $exe @args | Out-Null
 $code=$LASTEXITCODE
 $receipt=Get-Content -LiteralPath (Join-Path $run 'receipt.json') -Raw | ConvertFrom-Json
 if($code -ne $case.expectedExit -or !$receipt.sourceUnchanged -or $receipt.cleanup.forced -or $receipt.cleanup.remaining.Count -ne 0 -or !$receipt.worker.cleanup.quit){throw "Case $($case.name) failed: $code"}
 if($case.expectedExit -ne 0){
  if($receipt.failure.code -ne 'SELECTION_MISMATCH' -or (Test-Path -LiteralPath $out) -or (Test-Path -LiteralPath (Join-Path $root ($case.name+'.pdf')))){throw 'Wrong-target case wrote output or failed for another reason'}
  if(Select-String -LiteralPath (Join-Path $run 'events.jsonl') -Pattern 'paragraph.execute|document.saveAs' -Quiet){throw 'Wrong-target case reached mutation'}
 }
 $results+=@{case=$case.name;exit=$code;status=$receipt.status;sourceUnchanged=$receipt.sourceUnchanged;normalQuit=$receipt.worker.cleanup.quit}
}
$results | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $root 'regression.json') -Encoding UTF8
$results | ConvertTo-Json -Depth 6

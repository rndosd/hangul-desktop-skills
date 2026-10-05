# Pure checks; no COM instance is created.
. (Join-Path $PSScriptRoot 'Hancom.Cell.Common.ps1')
$start=@{list=5;para=0;pos=0}
if(!(Assert-GridParagraphRange $start @{list=5;para=0;pos=0} $true)){throw 'Expected zero range'}
if(Assert-GridParagraphRange $start @{list=5;para=0;pos=3} $false){throw 'Expected nonzero range'}
foreach($case in @(
    @{end=@{list=5;para=0;pos=0};empty=$false},
    @{end=@{list=5;para=0;pos=1};empty=$true},
    @{end=@{list=6;para=0;pos=0};empty=$true},
    @{end=@{list=5;para=1;pos=0};empty=$true}
)){
    $blocked=$false
    try{$null=Assert-GridParagraphRange $start $case.end $case.empty}catch{$blocked=$true}
    if(!$blocked){throw 'Invalid blank/range evidence accepted'}
}
'PASS_GRID_EMPTY_RANGE: 2 positive and 4 negative cases'

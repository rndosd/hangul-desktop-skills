[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CandidatePath,

    [ValidateSet('OpenOnly', 'SaveAs')]
    [string]$Mode = 'OpenOnly',

    [string]$OutputPath,

    [string]$ReceiptPath,

    [string]$PdfPath,

    [string]$RunDirectory,
    [string]$CompositionPlanPath,
    [string]$CompositionSha256,

    [ValidateRange(10, 300)]
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Hancom.OwnedExit.ps1')

function Quote-ProcessArgument([string]$Value) {
    if ($Value.Contains('"')) { throw 'Paths containing a double quote are not supported.' }
    return '"' + $Value + '"'
}

function Write-Receipt([System.Collections.IDictionary]$Receipt, [string]$Destination) {
    $json = $Receipt | ConvertTo-Json -Depth 6
    if (-not [string]::IsNullOrWhiteSpace($Destination)) {
        $absolute = [System.IO.Path]::GetFullPath($Destination)
        if (Test-Path -LiteralPath $absolute) {
            throw 'ReceiptPath already exists; refusing to overwrite it.'
        }
        [System.IO.File]::WriteAllText($absolute, $json, [System.Text.UTF8Encoding]::new($false))
    }
    return $json
}

function Get-HancomSourceSha256([string]$Path) {
    $stream=[IO.File]::OpenRead($Path)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose();$algorithm.Dispose() }
}

function Get-HancomInterruptedReceipt([string]$ProgressPath,[string]$Reason) {
    $last=$null;$invalidRows=0
    if (Test-Path -LiteralPath $ProgressPath) {
        foreach($line in [IO.File]::ReadLines($ProgressPath)) {
            try { $row=$line|ConvertFrom-Json -ErrorAction Stop; if($row.stage){$last=$row} }
            catch { $invalidRows++ }
        }
    }
    $result=[ordered]@{status='BLOCKED_COM';mode=$Mode;candidatePath=$candidate;finalPath=if($Mode -eq 'SaveAs'){[IO.Path]::GetFullPath($OutputPath)}else{$candidate};firstOpen=$null;saveAs=$null;reopen=$null;pageCountBefore=$null;pageCountAfter=$null}
    if($last.receipt){foreach($property in $last.receipt.PSObject.Properties){$result[$property.Name]=$property.Value}}
    $result.status='BLOCKED_COM'
    $result.error=$Reason
    $result.checkedAt=(Get-Date).ToString('o')
    $result.interrupted=$true
    $result.inFlightOutcome='UNKNOWN_DO_NOT_RETRY'
    $result.progress=@{path=$ProgressPath;lastStage=$last.stage;elapsedMs=$last.elapsedMs;utc=$last.utc;invalidRows=$invalidRows}
    $result.comCreated=$last.comCreated
    $result.registerModuleCalled=$last.registerModuleCalled
    $result.securityModuleRegistered=$last.securityModuleRegistered
    $result.registerModuleArguments=$last.registerModuleArguments
    $result.observationErrors=@()
    $result.cleanup=@{quit=$last.normalQuit;owned=($null -ne $last.owner);owner=$last.owner;forced=$false;remaining=$null;normalExitWait=$null}
    if($last.normalQuit -and $last.owner){$result.cleanup.normalExitWait=Wait-HancomOwnedExit -Owner $last.owner -LimitMs 10000}
    try {$result.cleanup.remaining=@(Get-Process Hwp -ErrorAction SilentlyContinue|ForEach-Object{$_.Id})}catch{$result.observationErrors+=@{operation='remaining-processes';error=$_.Exception.Message}}
    $result.sourceUnchanged=$null
    try {$result.sourceUnchanged=((Get-HancomSourceSha256 $candidate) -eq $sourceHashBefore)}catch{$result.observationErrors+=@{operation='source-hash';path=$candidate;error=$_.Exception.Message}}
    $result.artifacts=@()
    foreach($path in @($OutputPath,$PdfPath)) {
        try {
            if($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
                $result.artifacts+=@{path=[IO.Path]::GetFullPath($path);bytes=(Get-Item -LiteralPath $path).Length;completion='UNVERIFIED'}
            }
        }catch{$result.observationErrors+=@{operation='artifact-observation';path=$path;error=$_.Exception.Message}}
    }
    return $result
}

$candidate = (Resolve-Path -LiteralPath $CandidatePath -ErrorAction Stop).Path
if ($RunDirectory) {
    $run = [IO.Path]::GetFullPath($RunDirectory)
    if (Test-Path -LiteralPath $run) { throw 'RunDirectory must be new.' }
    if ($ReceiptPath) { throw 'Use RunDirectory or ReceiptPath, not both.' }
    $null = New-Item -ItemType Directory -Path $run
    $ReceiptPath = Join-Path $run 'receipt.json'
    $job = @{input=$candidate;output=if($Mode -eq 'SaveAs'){[IO.Path]::GetFullPath($OutputPath)}else{$candidate};pdf=if($PdfPath){[IO.Path]::GetFullPath($PdfPath)}else{$null};mode=$Mode;entrypoint='verify_hwpx_with_hancom.ps1'}
    [IO.File]::WriteAllText((Join-Path $run 'job.json'),($job|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}
foreach($path in @($ReceiptPath,$OutputPath,$PdfPath)) {
    if ($path -and (Test-Path -LiteralPath $path)) { throw 'Output or receipt already exists; no COM call issued.' }
}

# The worker calls Hwp.RegisterModule before Open. Do not gate on this Codex
# process's HKCU view because MSIX registry virtualization can make it differ
# from the registry view used by Hwp.exe.
$worker = Join-Path $PSScriptRoot 'hancom_worker.ps1'
$temporaryReceipt = Join-Path ([System.IO.Path]::GetTempPath()) ('hwpx-com-' + [guid]::NewGuid().ToString('N') + '.json')
$progressPath=if($PdfPath){[IO.Path]::GetFullPath($PdfPath)+'.progress.jsonl'}elseif($ReceiptPath){[IO.Path]::GetFullPath($ReceiptPath)+'.progress.jsonl'}else{$temporaryReceipt+'.progress.jsonl'}
$cancellationPath=$progressPath+'.cancel'
if((Test-Path -LiteralPath $progressPath) -or (Test-Path -LiteralPath $cancellationPath)){throw 'Progress or cancellation path already exists; no COM call issued.'}
$sourceHashBefore=Get-HancomSourceSha256 $candidate
$arguments = @(
    '-NoProfile', '-STA',
    '-File', (Quote-ProcessArgument $worker),
    '-CandidatePath', (Quote-ProcessArgument $candidate),
    '-Mode', $Mode,
    '-ReceiptPath', (Quote-ProcessArgument $temporaryReceipt),
    '-ProgressPath', (Quote-ProcessArgument $progressPath),
    '-CancellationPath', (Quote-ProcessArgument $cancellationPath)
)

if ($Mode -eq 'SaveAs') {
    if ([string]::IsNullOrWhiteSpace($OutputPath)) { throw 'OutputPath is required in SaveAs mode.' }
    $arguments += @('-OutputPath', (Quote-ProcessArgument ([System.IO.Path]::GetFullPath($OutputPath))))
}

if ($CompositionPlanPath) {
    if ($Mode -ne 'SaveAs' -or !$CompositionSha256) { throw 'Composition requires SaveAs and a plan hash.' }
    $arguments += @('-CompositionPlanPath',(Quote-ProcessArgument ([IO.Path]::GetFullPath($CompositionPlanPath))),'-CompositionSha256',$CompositionSha256)
}
$process = $null
if (-not [string]::IsNullOrWhiteSpace($PdfPath)) {
    $arguments += @('-PdfPath', (Quote-ProcessArgument ([System.IO.Path]::GetFullPath($PdfPath))))
}
$mutex = [Threading.Mutex]::new($false,'Local\CodexHancomAutomation')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'LOCK_CONFLICT: another common runner owns COM.' }
    if (@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -ne 0) { throw 'PROCESS_CONFLICT: existing Hangul process; no COM call issued.' }
    $launch=@{FilePath=(Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/powershell.exe');ArgumentList=($arguments -join ' ');WindowStyle='Hidden';PassThru=$true}
    if($RunDirectory){$launch.RedirectStandardOutput=Join-Path $run 'stdout.log';$launch.RedirectStandardError=Join-Path $run 'stderr.log'}
    $process = Start-Process @launch
    $workerIdentity=@{pid=$process.Id;startTicks=$process.StartTime.ToUniversalTime().Ticks}
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        [IO.File]::WriteAllText($cancellationPath,'Cancellation requested by controller timeout.',[Text.UTF8Encoding]::new($false))
        $workerExited=$process.WaitForExit(5000)
        $receipt = Get-HancomInterruptedReceipt $progressPath "Hancom COM worker timed out after $TimeoutSeconds seconds. Cancellation is requested; inspect the last stage and owned process before any retry."
        $receipt.worker=@{pid=$workerIdentity.pid;startTicks=$workerIdentity.startTicks;exited=$workerExited;forced=$false;receiptPath=$temporaryReceipt;cancellationPath=$cancellationPath}
        Write-Receipt $receipt $ReceiptPath
        exit 3
    }

    if (-not (Test-Path -LiteralPath $temporaryReceipt)) {
        $receipt = Get-HancomInterruptedReceipt $progressPath "Hancom COM worker exited with code $($process.ExitCode) without producing a receipt."
        Write-Receipt $receipt $ReceiptPath
        exit 3
    }

    $receiptObject = Get-Content -Raw -Encoding UTF8 -LiteralPath $temporaryReceipt | ConvertFrom-Json
    $waitInfo=@{limitMs=10000;identityMatched=$null;waited=$false;exited=$null;identityError=$null}
    if ($receiptObject.cleanup.quit -and $receiptObject.cleanup.owned -and $receiptObject.cleanup.owner) {
        $waitInfo=Wait-HancomOwnedExit -Owner $receiptObject.cleanup.owner -LimitMs 10000
    }
    $receiptObject.cleanup | Add-Member -NotePropertyName normalExitWait -NotePropertyValue $waitInfo -Force
    if ($waitInfo.identityError) { $receiptObject.status='BLOCKED_COM' }
    $remaining=@(Get-Process Hwp -ErrorAction SilentlyContinue|ForEach-Object{$_.Id})
    $receiptObject.cleanup | Add-Member -NotePropertyName remaining -NotePropertyValue $remaining -Force
    if($remaining.Count -gt 0 -or !$receiptObject.cleanup.quit -or !$receiptObject.sourceUnchanged){$receiptObject.status='BLOCKED_COM'}
    $json = $receiptObject | ConvertTo-Json -Depth 6
    if (-not [string]::IsNullOrWhiteSpace($ReceiptPath)) {
        $absoluteReceipt = [System.IO.Path]::GetFullPath($ReceiptPath)
        if (Test-Path -LiteralPath $absoluteReceipt) {
            throw 'ReceiptPath already exists; refusing to overwrite it.'
        }
        [System.IO.File]::WriteAllText($absoluteReceipt, $json, [System.Text.UTF8Encoding]::new($false))
    }
    $json
    if ($receiptObject.status -ne 'PASS_FULL') { exit 3 }
}
finally {
    if($locked){$mutex.ReleaseMutex()};$mutex.Dispose()
    if (-not (Test-Path -LiteralPath $cancellationPath) -and (Test-Path -LiteralPath $temporaryReceipt)) {
        Remove-Item -LiteralPath $temporaryReceipt -Force
    }
}

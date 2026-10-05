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
$arguments = @(
    '-NoProfile', '-STA',
    '-File', (Quote-ProcessArgument $worker),
    '-CandidatePath', (Quote-ProcessArgument $candidate),
    '-Mode', $Mode,
    '-ReceiptPath', (Quote-ProcessArgument $temporaryReceipt)
)

if ($Mode -eq 'SaveAs') {
    if ([string]::IsNullOrWhiteSpace($OutputPath)) { throw 'OutputPath is required in SaveAs mode.' }
    $arguments += @('-OutputPath', (Quote-ProcessArgument ([System.IO.Path]::GetFullPath($OutputPath))))
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
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        try { Stop-Process -Id $process.Id -Force -ErrorAction Stop } catch {}
        $receipt = [ordered]@{
            status = 'BLOCKED_COM'
            mode = $Mode
            candidatePath = $candidate
            finalPath = if ($Mode -eq 'SaveAs') { [System.IO.Path]::GetFullPath($OutputPath) } else { $candidate }
            firstOpen = $false
            saveAs = $false
            reopen = $false
            pageCountBefore = $null
            pageCountAfter = $null
            error = "Hancom COM worker timed out after $TimeoutSeconds seconds. A hidden Hangul process may require manual closing."
            checkedAt = (Get-Date).ToString('o')
        }
        Write-Receipt $receipt $ReceiptPath
        exit 3
    }

    if (-not (Test-Path -LiteralPath $temporaryReceipt)) {
        $receipt = [ordered]@{
            status = 'BLOCKED_COM'
            mode = $Mode
            candidatePath = $candidate
            finalPath = if ($Mode -eq 'SaveAs') { [System.IO.Path]::GetFullPath($OutputPath) } else { $candidate }
            error = "Hancom COM worker exited with code $($process.ExitCode) without producing a receipt."
            checkedAt = (Get-Date).ToString('o')
        }
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
    if (Test-Path -LiteralPath $temporaryReceipt) {
        Remove-Item -LiteralPath $temporaryReceipt -Force
    }
}

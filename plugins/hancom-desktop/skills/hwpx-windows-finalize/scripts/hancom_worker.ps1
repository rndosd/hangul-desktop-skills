[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CandidatePath,

    [ValidateSet('OpenOnly', 'SaveAs')]
    [string]$Mode = 'OpenOnly',

    [string]$OutputPath,

    [string]$ReceiptPath,
    [string]$PdfPath,
    [string]$ProgressPath,
    [string]$CancellationPath,
    [string]$CompositionPlanPath,
    [string]$CompositionSha256
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Hancom.Environment.ps1')
$script:Owned=$false
$script:NormalQuit=$false
$script:Owner=$null
$script:ComCreated=$false
$script:RegisterModuleCalled=$false
$script:SecurityModuleRegistered=$null
$script:RegisterModuleName=$null
$script:StageClock=[Diagnostics.Stopwatch]::StartNew()
$script:LastStageMs=0
$script:Closing=$false
$script:WorkerIdentity=@{pid=$PID;startTicks=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks}



function Write-HancomStage([string]$Stage) {
    $cancelled=$CancellationPath -and (Test-Path -LiteralPath $CancellationPath)
    if($cancelled){$receipt.cancellationRequested=$true}
    if ([string]::IsNullOrWhiteSpace($ProgressPath)) { return }
    $elapsed=$script:StageClock.ElapsedMilliseconds
    $row=@{stage=$Stage;utc=[DateTime]::UtcNow.ToString('o');elapsedMs=$elapsed;sincePreviousStageMs=($elapsed-$script:LastStageMs);receipt=$receipt;worker=$script:WorkerIdentity;comCreated=$script:ComCreated;registerModuleCalled=$script:RegisterModuleCalled;securityModuleRegistered=$script:SecurityModuleRegistered;registerModuleArguments=if($script:RegisterModuleCalled){@('FilePathCheckDLL',$script:RegisterModuleName)}else{$null};owner=$script:Owner;normalQuit=$script:NormalQuit}
    [IO.File]::AppendAllText($ProgressPath,(($row|ConvertTo-Json -Depth 7 -Compress)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
    $script:LastStageMs=$elapsed
    if($cancelled -and !$script:Closing -and $Stage -ne 'com-created'){throw 'CANCELLED_BY_CONTROLLER: interrupted operation requires artifact review before retry.'}
}

function Get-FinalizeSha256([string]$Path) {
    $stream=[IO.File]::OpenRead($Path)
    $algorithm=[Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','') }
    finally { $stream.Dispose();$algorithm.Dispose() }
}
function Get-AbsoluteExistingPath([string]$Path) {
    return (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
}

function Get-HancomPageCount($Hwp) {
    try { return [int]$Hwp.PageCount } catch {}
    try { return [int]$Hwp.GetPageCount() } catch {}
    return $null
}

function New-HancomObject {
    if(@(Get-Process Hwp -ErrorAction SilentlyContinue).Count -ne 0){throw 'PROCESS_CONFLICT: existing Hangul process.'}
    $securityModuleName=Assert-HancomSecurityBinding (Get-HancomEnvironment)
    $birth=[DateTime]::UtcNow
    $object = New-Object -ComObject HWPFrame.HwpObject
    $script:ComCreated=$true
    Write-HancomStage 'com-created'
    try {
        Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class FinalizeWindowPid { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); }'
        $window=$object.XHwpWindows.Item(0)
        $hwnd=[IntPtr]([long]$window.WindowHandle)
        [uint32]$serverId=0
        $null=[FinalizeWindowPid]::GetWindowThreadProcessId($hwnd,[ref]$serverId)
        $server=Get-Process -Id $serverId
        if($server.ProcessName -ne 'Hwp' -or $server.StartTime.ToUniversalTime() -lt $birth.AddSeconds(-1)){throw 'OWNERSHIP_UNPROVEN: COM window process identity.'}
        $script:Owner=@{pid=$server.Id;startTicks=$server.StartTime.ToUniversalTime().Ticks;path=$server.Path;hwnd=$hwnd.ToInt64()}
        $script:Owned=$true
        Write-HancomStage 'owner-confirmed'
        $script:RegisterModuleCalled=$true
        $script:RegisterModuleName=[string]$securityModuleName
        Write-HancomStage 'module-start'
        $registered = $object.RegisterModule('FilePathCheckDLL', [string]$securityModuleName)
        $script:SecurityModuleRegistered=[bool]$registered
        Write-HancomStage 'module-result'
        if (-not $registered) {
            throw 'Security module registration returned false. No document was opened. Verify the approved Automation module and its registry entry.'
        }
        try { $object.XHwpWindows.Item(0).Visible = $false } catch {}
        return $object
    }
    catch {
        Close-HancomObject $object
        throw
    }
}

function Close-HancomObject($Hwp) {
    if ($null -eq $Hwp) { return }
    $script:Closing=$true
    if($script:Owned) {
        Write-HancomStage 'cleanup-clear-start'
        try { $Hwp.Clear(1) } catch {}
        Write-HancomStage 'cleanup-clear-done'
        Write-HancomStage 'cleanup-quit-start'
        try { $Hwp.Quit(); $script:NormalQuit=$true } catch {}
        Write-HancomStage 'cleanup-quit-done'
    }
    try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Hwp) } catch {}
}

$candidate = Get-AbsoluteExistingPath $CandidatePath
if ([System.IO.Path]::GetExtension($candidate) -ine '.hwpx') {
    throw 'CandidatePath must be an .hwpx file.'
}

$sourceHashBefore=(Get-FinalizeSha256 $candidate)
if (-not $ProgressPath) {
    if ($PdfPath) { $ProgressPath=[IO.Path]::GetFullPath($PdfPath)+'.progress.jsonl' }
    elseif ($ReceiptPath) { $ProgressPath=[IO.Path]::GetFullPath($ReceiptPath)+'.progress.jsonl' }
}
if ($ProgressPath) {
    $ProgressPath=[IO.Path]::GetFullPath($ProgressPath)
    $stream=[IO.File]::Open($ProgressPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
    $stream.Dispose()
}
$finalPath = $candidate
if ($Mode -eq 'SaveAs') {
    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        throw 'OutputPath is required in SaveAs mode.'
    }
    $finalPath = [System.IO.Path]::GetFullPath($OutputPath)
    if ($finalPath -eq $candidate) {
        throw 'OutputPath must differ from CandidatePath.'
    }
    if (Test-Path -LiteralPath $finalPath) {
        throw 'OutputPath already exists; refusing to overwrite it.'
    }
    $parent = Split-Path -Parent $finalPath
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw 'OutputPath parent directory does not exist.'
    }
}

$receipt = [ordered]@{
    evidenceSchema = 'hwpx.hancom-finalize.v2'
    sourceSha256Before = $sourceHashBefore
    status = 'BLOCKED_COM'
    mode = $Mode
    candidatePath = $candidate
    finalPath = $finalPath
    firstOpen = $false
    saveAs = $false
    reopen = $false
    pdfExport = $false
    pageCountBefore = $null
    pageCountAfter = $null
    error = $null
    checkedAt = (Get-Date).ToString('o')
}

$composition=$null
if($CompositionPlanPath){. (Join-Path $PSScriptRoot 'Hancom.Composition.ps1')}
$hwp = $null
$workerMutex=[Threading.Mutex]::new($false,'Local\CodexHancomAutomationWorker')
$workerLocked=$false
try {
    try { $workerLocked=$workerMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $workerLocked=$true }
    if(!$workerLocked){throw 'LOCK_CONFLICT: another native worker is still running.'}
    if($CompositionPlanPath){
        if($Mode -ne 'SaveAs' -or !$PdfPath){throw 'Composition requires SaveAs and PDF.'}
        $composition=Read-HancomComposition $CompositionPlanPath $CompositionSha256 $candidate $sourceHashBefore
        $receipt.composition=@{planSha256=$CompositionSha256;inserted=@();basePageCount=$null;inputChecks=@();visual='NOT_REVIEWED';fullPreservation='NOT_CHECKED'}
    }
    Write-HancomStage 'com-start'
    $hwp = New-HancomObject
    Write-HancomStage 'com-and-module-done'
    Write-HancomStage 'version-start'
    $receipt.version=[string]$hwp.Version
    Write-HancomStage 'version-done'
    Write-HancomStage 'first-open-start'
    $opened = $hwp.Open($candidate, '', '')
    if ($opened -eq $false) { throw 'Hancom returned false while opening the candidate.' }
    $receipt.firstOpen = $true
    Write-HancomStage 'first-open-done'
    if($composition){
        $receipt.composition.basePageCount=Get-HancomPageCount $hwp
        Invoke-HancomComposition $hwp $composition $receipt.composition
    }
    # Round-trip page count starts after intentional composition, before SaveAs.
    Write-HancomStage 'page-count-before-start'
    $receipt.pageCountBefore = Get-HancomPageCount $hwp
    Write-HancomStage 'page-count-before-done'

    if ($Mode -eq 'SaveAs') {
        Write-HancomStage 'hwpx-save-start'
        $saved = $hwp.SaveAs($finalPath, 'HWPX', '')
        if ($saved -eq $false) { throw 'Hancom returned false while saving the final file.' }
        $receipt.saveAs = $true
        Write-HancomStage 'hwpx-save-done'
    }

    # Reload the document in the existing application. Immediate Quit/New can
    # reuse a disconnecting COM class factory (RPC_E_DISCONNECTED).
    Write-HancomStage 'reopen-clear-start'
    $hwp.Clear(1)
    Write-HancomStage 'reopen-clear-done'
    Write-HancomStage 'reopen-open-start'
    $reopened = $hwp.Open($finalPath, '', '')
    if ($reopened -eq $false) { throw 'Hancom returned false while reopening the final file.' }
    $receipt.reopen = $true
    Write-HancomStage 'reopen-open-done'
    Write-HancomStage 'page-count-after-start'
    $receipt.pageCountAfter = Get-HancomPageCount $hwp
    Write-HancomStage 'page-count-after-done'

    if (-not [string]::IsNullOrWhiteSpace($PdfPath)) {
        $pdfAbsolute = [System.IO.Path]::GetFullPath($PdfPath)
        if (Test-Path -LiteralPath $pdfAbsolute) { throw 'PdfPath already exists.' }
        Write-HancomStage 'pdf-export-start'
        if (-not $hwp.SaveAs($pdfAbsolute, 'PDF', '')) { throw 'PDF export failed.' }
        Write-HancomStage 'pdf-export-done'
        $receipt.pdfExport = Test-Path -LiteralPath $pdfAbsolute -PathType Leaf
        if (-not $receipt.pdfExport) { throw 'PDF file missing after export.' }
    }

    if ($null -ne $receipt.pageCountBefore -and $null -ne $receipt.pageCountAfter -and
        $receipt.pageCountBefore -ne $receipt.pageCountAfter) {
        throw "Page count changed from $($receipt.pageCountBefore) to $($receipt.pageCountAfter)."
    }

    $receipt.status = 'PASS_FULL'
}
catch {
    $receipt.error = $_.Exception.Message
}
finally {
    try { Close-HancomObject $hwp }
    finally {if($workerLocked){$workerMutex.ReleaseMutex()};$workerMutex.Dispose()}
}

$receipt.comCreated=$script:ComCreated
$receipt.registerModuleCalled=$script:RegisterModuleCalled
$receipt.securityModuleRegistered=$script:SecurityModuleRegistered
$receipt.registerModuleArguments=if($script:RegisterModuleCalled){@('FilePathCheckDLL',$script:RegisterModuleName)}else{$null}
$receipt.sourceSha256After=(Get-FinalizeSha256 $candidate)
$receipt.sourceUnchanged=($receipt.sourceSha256After -eq $sourceHashBefore)
$receipt.cleanup=@{quit=$script:NormalQuit;owned=$script:Owned;forced=$false;owner=$script:Owner;remaining=@()}
if($composition){
    $receipt.composition.inputChecks=@(Test-HancomCompositionInputs $composition $candidate $receipt.sourceSha256After)
    if(@($receipt.composition.inputChecks | Where-Object { !$_.unchanged }).Count -gt 0){$receipt.status='BLOCKED_COM'}
}
$receipt.artifacts=@()
foreach($path in @($finalPath,$PdfPath)){
    if($path -and (Test-Path -LiteralPath $path -PathType Leaf)){
        $receipt.artifacts+=@{path=[IO.Path]::GetFullPath($path);sha256=(Get-FinalizeSha256 $path);bytes=(Get-Item -LiteralPath $path).Length}
    }
}
$receipt.visual='NOT_REVIEWED'
$receipt.structuralPreservation='NOT_CHECKED'
$receipt.nonTargetPreservation='NOT_CHECKED'
if(!$receipt.sourceUnchanged -or !$script:NormalQuit){$receipt.status='BLOCKED_COM'}
$json = $receipt | ConvertTo-Json -Depth 7
if (-not [string]::IsNullOrWhiteSpace($ReceiptPath)) {
    $receiptAbsolute = [System.IO.Path]::GetFullPath($ReceiptPath)
    if (Test-Path -LiteralPath $receiptAbsolute) {
        throw 'ReceiptPath already exists; refusing to overwrite it.'
    }
    [System.IO.File]::WriteAllText($receiptAbsolute, $json, [System.Text.UTF8Encoding]::new($false))
}
$json
if ($receipt.status -ne 'PASS_FULL') { exit 3 }

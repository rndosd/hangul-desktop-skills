[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$CandidatePath,

    [ValidateSet('OpenOnly', 'SaveAs')]
    [string]$Mode = 'OpenOnly',

    [string]$OutputPath,

    [string]$ReceiptPath,
    [string]$PdfPath
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



function Write-HancomStage([string]$Stage) {
    if ([string]::IsNullOrWhiteSpace($PdfPath)) { return }
    $row=@{stage=$Stage;utc=[DateTime]::UtcNow.ToString('o');comCreated=$script:ComCreated;registerModuleCalled=$script:RegisterModuleCalled;securityModuleRegistered=$script:SecurityModuleRegistered;registerModuleArguments=if($script:RegisterModuleCalled){@('FilePathCheckDLL',$script:RegisterModuleName)}else{$null};owner=$script:Owner;normalQuit=$script:NormalQuit}
    [IO.File]::AppendAllText(([IO.Path]::GetFullPath($PdfPath)+'.progress.jsonl'),(($row|ConvertTo-Json -Depth 5 -Compress)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
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
        $script:RegisterModuleCalled=$true
        $script:RegisterModuleName=[string]$securityModuleName
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

$hwp = $null
try {
    Write-HancomStage 'com-start'
    $hwp = New-HancomObject
    Write-HancomStage 'com-and-module-done'
    $receipt.version=[string]$hwp.Version
    Write-HancomStage 'first-open-start'
    $opened = $hwp.Open($candidate, '', '')
    if ($opened -eq $false) { throw 'Hancom returned false while opening the candidate.' }
    $receipt.firstOpen = $true
    Write-HancomStage 'first-open-done'
    $receipt.pageCountBefore = Get-HancomPageCount $hwp

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
    $receipt.pageCountAfter = Get-HancomPageCount $hwp

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
    Close-HancomObject $hwp
}

$receipt.comCreated=$script:ComCreated
$receipt.registerModuleCalled=$script:RegisterModuleCalled
$receipt.securityModuleRegistered=$script:SecurityModuleRegistered
$receipt.registerModuleArguments=if($script:RegisterModuleCalled){@('FilePathCheckDLL',$script:RegisterModuleName)}else{$null}
$receipt.sourceSha256After=(Get-FinalizeSha256 $candidate)
$receipt.sourceUnchanged=($receipt.sourceSha256After -eq $sourceHashBefore)
$receipt.cleanup=@{quit=$script:NormalQuit;owned=$script:Owned;forced=$false;owner=$script:Owner;remaining=@()}
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

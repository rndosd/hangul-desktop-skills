param([Parameter(Mandatory)][string]$PlanPath)
# Build-time Hangul steps for tools/build_assembly_template.py: block-save source ranges, or render
# calibration PDFs of prepared parts. Owns exactly one Hangul instance and quits only that one.
$ErrorActionPreference = 'Stop'
$plan = Get-Content -Raw -Encoding UTF8 -LiteralPath $PlanPath | ConvertFrom-Json
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$environment = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $codexRoot 'skills/hwpx/environment.json') | ConvertFrom-Json
$report = [ordered]@{ checks = @(); saved = @(); rendered = @(); error = $null }
$mutex = [Threading.Mutex]::new($false, 'Local\CodexHancomAutomation')
$locked = $false
$hwp = $null
function Get-ParagraphText([int]$Index) {
    [void]$hwp.SelectText($Index, 0, $Index + 1, 0)
    $text = [string]$hwp.GetTextFile('TEXT', 'saveblock')
    $hwp.Run('Cancel')
    return [Net.WebUtility]::HtmlDecode($text).Trim()  # Hangul returns some symbols as &#NNNNN;
}
function Find-Backward([string]$Text) {
    [void]$hwp.Run('MoveDocEnd')
    $set = $hwp.HParameterSet.HFindReplace
    [void]$hwp.HAction.GetDefault('RepeatFind', $set.HSet)
    $set.FindString = $Text; $set.IgnoreMessage = 1; $set.FindRegExp = 0; $set.Direction = $hwp.FindDir('Backward')
    [void]$hwp.HAction.Execute('RepeatFind', $set.HSet)
    $found = [Net.WebUtility]::HtmlDecode([string]$hwp.GetTextFile('TEXT', 'saveblock')).Trim()
    if ($found -ne $Text) { throw "PLACEHOLDER_NOT_FOUND: $Text" }
}
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (!$locked) { throw 'LOCK_CONFLICT: another native runner owns Hangul.' }
    if (@(Get-Process Hwp -ErrorAction SilentlyContinue).Count) { throw 'PROCESS_CONFLICT: Hangul is already running.' }
    $hwp = New-Object -ComObject HWPFrame.HwpObject
    $hwp.XHwpWindows.Item(0).Visible = $false
    if (-not $hwp.RegisterModule('FilePathCheckDLL', [string]$environment.security.moduleName)) { throw 'SECURITY_MODULE_NOT_REGISTERED' }
    if ($plan.source) {
        if (-not $hwp.Open([string]$plan.source, 'HWPX', 'forceopen:true')) { throw 'SOURCE_OPEN_FAILED' }
        foreach ($block in $plan.blocks) {
            if ($block.check) {
                $actual = Get-ParagraphText ([int]$block.check.paragraph)
                $ok = $actual.StartsWith([string]$block.check.startsWith)
                $report.checks += [ordered]@{ name = $block.name; paragraph = $block.check.paragraph; ok = $ok; actual = $actual.Substring(0, [Math]::Min(40, $actual.Length)) }
                if (!$ok) { throw "RANGE_CHECK_FAILED: $($block.name)" }
            }
            [void]$hwp.SelectText([int]$block.start, 0, [int]$block.end, 0)
            $set = $hwp.HParameterSet.HFileOpenSave
            [void]$hwp.HAction.GetDefault('FileSaveBlock_S', $set.HSet)
            $set.filename = [string]$block.path; $set.Format = 'HWPX'
            $ok = $hwp.HAction.Execute('FileSaveBlock_S', $set.HSet)
            $hwp.Run('Cancel')
            if (!$ok -or !(Test-Path -LiteralPath $block.path)) { throw "BLOCK_SAVE_FAILED: $($block.name)" }
            $report.saved += [ordered]@{ name = $block.name; path = $block.path }
        }
    }
    foreach ($render in $plan.renders) {
        if (-not $hwp.Open([string]$render.part, 'HWPX', 'forceopen:true')) { throw "PART_OPEN_FAILED: $($render.part)" }
        if ($render.find) {
            Find-Backward ([string]$render.find)
            $text = $hwp.HParameterSet.HInsertText
            [void]$hwp.HAction.GetDefault('InsertText', $text.HSet); $text.Text = [string]$render.text
            [void]$hwp.HAction.Execute('InsertText', $text.HSet)
        }
        if ($render.boxWidth) {
            $box = $null; $control = $hwp.HeadCtrl
            while ($control) { if ($control.CtrlID -eq 'gso') { $box = $control }; $control = $control.Next }
            $size = $hwp.CreateSet('ShapeObject'); $size.SetItem('Width', [int]$render.boxWidth); $box.Properties = $size
        }
        if (-not $hwp.SaveAs([string]$render.pdf, 'PDF', '')) { throw "PDF_EXPORT_FAILED: $($render.pdf)" }
        $report.rendered += [ordered]@{ part = $render.part; pdf = $render.pdf }
        $hwp.Clear(1)
    }
} catch { $report.error = $_.Exception.Message }
finally {
    if ($hwp) { try { $hwp.Clear(1) } catch {}; try { $hwp.Quit() } catch {}; [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) }
    if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose()
}
$report | ConvertTo-Json -Depth 5
if ($report.error) { exit 3 }

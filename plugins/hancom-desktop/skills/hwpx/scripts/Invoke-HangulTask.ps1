param([Parameter(ValueFromRemainingArguments=$true)][string[]]$TaskArguments)
$ErrorActionPreference = 'Stop'
$taskSkillRoot = Split-Path -Parent $PSScriptRoot
$taskConfigPath = Join-Path $taskSkillRoot 'environment.json'
if (!(Test-Path -LiteralPath $taskConfigPath -PathType Leaf)) {
    $taskCodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $taskConfigPath = Join-Path $taskCodexRoot 'skills/hwpx/environment.json'
}
if (!(Test-Path -LiteralPath $taskConfigPath -PathType Leaf)) { throw 'environment.json 없음. 이 PC의 설치 안내를 확인하세요.' }
$taskConfig = Get-Content -LiteralPath $taskConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (!$taskConfig.pythonPath -or !(Test-Path -LiteralPath $taskConfig.pythonPath -PathType Leaf)) { throw '설정된 Python 경로가 없습니다. 설정을 자동으로 변경하지 않습니다.' }
& $taskConfig.pythonPath -X utf8 -B (Join-Path $PSScriptRoot 'hangul_task.py') @TaskArguments
exit $LASTEXITCODE

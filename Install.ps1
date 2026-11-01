[CmdletBinding()]
param(
    [string]$CodexRoot,
    [string]$PythonPath,
    [switch]$CheckOnly,
    [switch]$NoDependencyInstall,
    [switch]$AcceptGlobalFileAccess,
    [ValidateSet('Auto','Yes','No')][string]$Claude='Auto',
    [string]$ClaudeSkillsRoot
)
$ErrorActionPreference='Stop'
if(!$CodexRoot){$CodexRoot=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}}
$package=Join-Path $PSScriptRoot 'plugins/hancom-desktop'
$installer=Join-Path $package 'Install-HangulSkills.ps1'
$targets=@{Claude=$Claude}
if($ClaudeSkillsRoot){$targets.ClaudeSkillsRoot=$ClaudeSkillsRoot}
if($CheckOnly){
    & $installer -CodexRoot $CodexRoot -PythonPath $PythonPath -CheckOnly @targets
    exit $LASTEXITCODE
}
if($AcceptGlobalFileAccess){
    if($NoDependencyInstall){throw 'NoDependencyInstall and official module setup are separate choices; use the package installer to select an already reviewed module.'}
    & (Join-Path $package 'Setup-OfficialModule.ps1') -CodexRoot $CodexRoot -PythonPath $PythonPath -AcceptGlobalFileAccess @targets
    exit
}
if(!$PythonPath -and !$NoDependencyInstall){
    $probe=& powershell.exe -NoProfile -File $installer -CodexRoot $CodexRoot -CheckOnly
    if($LASTEXITCODE -ne 0){throw 'Read-only setup preflight failed.'}
    $environment=$probe|ConvertFrom-Json
    if($environment.coreStatus -eq 'python_3_12_missing'){
        $PythonPath=(& (Join-Path $package 'Bootstrap-Python.ps1') -CodexRoot $CodexRoot|Select-Object -Last 1)
    }
}
& $installer -CodexRoot $CodexRoot -PythonPath $PythonPath -NoDependencyInstall:$NoDependencyInstall @targets

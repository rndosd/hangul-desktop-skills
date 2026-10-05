[CmdletBinding()]
param(
    [string]$CodexRoot,
    [string]$PythonPath,
    [switch]$NoDependencyInstall,
    [switch]$CheckOnly,
    [string]$SecurityModuleName,
    [string]$SecurityDllSha256,
    [string]$SecurityPolicyPath,
    [switch]$ConfirmReviewedSecurityModule
)
$ErrorActionPreference='Stop'
$source=[IO.Path]::GetFullPath($PSScriptRoot)
if(!$CodexRoot){$CodexRoot=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}}
$CodexRoot=[IO.Path]::GetFullPath($CodexRoot)
. (Join-Path $source 'skills/hwpx-windows-finalize/scripts/Hancom.Environment.ps1')
function Read-Python([string]$Exe){
    if(!$Exe -or !(Test-Path -LiteralPath $Exe -PathType Leaf)){return $null}
    $code="import sys,json,importlib.metadata as m; ns=['python-hwpx','python-hwpx-automation','lxml','PyMuPDF','pypdf']; print(json.dumps({'exe':sys.executable,'version':list(sys.version_info[:3]),'packages':{n:next((d.version for d in m.distributions(name=n)),None) for n in ns}}))"
    try{$text=& $Exe -B -c $code 2>$null;if($LASTEXITCODE -eq 0){return ($text|ConvertFrom-Json)}}catch{}
    return $null
}
function Test-Core($Info){
    return ($null -ne $Info -and $Info.version[0] -eq 3 -and $Info.version[1] -eq 12 -and
      $Info.packages.'python-hwpx' -eq '6.3.0' -and $Info.packages.'python-hwpx-automation' -eq '7.0.3' -and
      $Info.packages.lxml -eq '6.1.3' -and $Info.packages.PyMuPDF -eq '1.28.2')
}
function Write-Json($Value,[string]$Path){[IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 14),[Text.UTF8Encoding]::new($false))}
function Assert-Child([string]$Path,[string]$Parent){
    $full=[IO.Path]::GetFullPath($Path);$prefix=[IO.Path]::GetFullPath($Parent).TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar
    if(!$full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Path outside intended installation directory.'}
    $current=$full
    while($current){
        if((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw ('Refusing reparse point: '+$current)}
        $next=Split-Path -Parent $current
        if($next -eq $current){break};$current=$next
    }
}
# A package manifest guards transfer errors, not publisher trust.
$manifest=Get-Content -LiteralPath (Join-Path $source 'PAYLOAD-SHA256.json') -Raw -Encoding UTF8|ConvertFrom-Json
foreach($entry in $manifest.PSObject.Properties){
    $path=Join-Path $source $entry.Name;Assert-Child $path $source
    if(!(Test-Path -LiteralPath $path -PathType Leaf) -or (Get-HancomSecuritySha256 $path) -ine $entry.Value){throw ('Package hash mismatch: '+$entry.Name)}
}
$candidates=@()
if($PythonPath){$candidates+=([IO.Path]::GetFullPath($PythonPath))}
if(!$PythonPath){
    $candidates+=@(Join-Path $CodexRoot 'runtimes/hwpx-desktop-v1/Scripts/python.exe')
    $candidates+=@(Join-Path $CodexRoot 'runtimes/hwpx/Scripts/python.exe')
    $py=Get-Command py.exe -ErrorAction SilentlyContinue
    if($py){try{$candidate=& $py.Source -3.12 -c 'import sys;print(sys.executable)' 2>$null;if($LASTEXITCODE -eq 0){$candidates+=[string]$candidate}}catch{}}
    $command=Get-Command python.exe -ErrorAction SilentlyContinue;if($command){$candidates+=$command.Source}
}
$python=$null;$basePython=$null
foreach($candidate in @($candidates|Select-Object -Unique)){
    $info=Read-Python $candidate
    if(Test-Core $info){$python=$info;break}
    if(!$basePython -and $info -and $info.version[0] -eq 3 -and $info.version[1] -eq 12){$basePython=$info}
}
if($PythonPath -and !$python -and !$basePython){throw 'The specified -PythonPath is not a usable Python 3.12 executable.'}
if(!$python -and $basePython -and !$NoDependencyInstall -and !$CheckOnly){
    $venv=Join-Path $CodexRoot 'runtimes/hwpx-desktop-v1'
    Assert-Child $venv $CodexRoot
    if(Test-Path -LiteralPath $venv){throw 'Existing managed Python environment is incomplete. It was not overwritten; pass a working -PythonPath or inspect this environment.'}
    & $basePython.exe -m venv $venv
    if($LASTEXITCODE -ne 0){throw 'Virtual environment creation failed.'}
    $venvPython=Join-Path $venv 'Scripts/python.exe'
    & $venvPython -m pip install -r (Join-Path $source 'requirements-core.txt')
    if($LASTEXITCODE -ne 0){throw 'Python dependency installation failed. Existing skills have not been replaced.'}
    & $venvPython -m pip check
    if($LASTEXITCODE -ne 0){throw 'Python dependency check failed.'}
    $python=Read-Python $venvPython
    if(!(Test-Core $python)){throw 'Python validation failed.'}
}
$hancom=Get-HancomDesktopInstallation
$security=[ordered]@{status='not_configured';reason='A reviewed security module has not been selected.';moduleName=$null;dllPath=$null;sha256=$null;policyPath=$null;policySha256=$null;reviewConfirmed=$false}
$existingConfig=Join-Path $CodexRoot 'skills/hwpx-windows-finalize/environment.json'
if(!$SecurityModuleName -and !$SecurityDllSha256 -and !$SecurityPolicyPath -and !$ConfirmReviewedSecurityModule -and (Test-Path -LiteralPath $existingConfig)){
    try{
        $oldEnvironment=Get-Content -LiteralPath $existingConfig -Raw -Encoding UTF8|ConvertFrom-Json
        if($oldEnvironment.security.status -eq 'reviewed_existing'){
            $null=Assert-HancomSecurityBinding $oldEnvironment
            foreach($property in $oldEnvironment.security.PSObject.Properties){$security[$property.Name]=$property.Value}
        }
    }catch{$security.reason=('Previous security configuration no longer passes validation: '+$_.Exception.Message)}
}
if($SecurityModuleName -or $SecurityDllSha256 -or $SecurityPolicyPath -or $ConfirmReviewedSecurityModule){
    if(!$SecurityModuleName -or $SecurityDllSha256 -notmatch '^[0-9a-fA-F]{64}$' -or !$SecurityPolicyPath -or !$ConfirmReviewedSecurityModule){throw 'Selecting an existing security module requires its name, SHA256, reviewed policy file, and -ConfirmReviewedSecurityModule. No module is selected automatically.'}
    $policy=(Resolve-Path -LiteralPath $SecurityPolicyPath).Path
    if(!(Test-Path -LiteralPath $policy -PathType Leaf)){throw 'Policy evidence must be a file.'}
    $binding=Get-HancomRegisteredModule $SecurityModuleName
    if(!$binding -or $binding.kind -ne 'String' -or !$binding.path){throw 'The requested module is not already registered as REG_SZ. This installer does not write registry entries.'}
    $security=[ordered]@{status='reviewed_existing';reason=$null;moduleName=$SecurityModuleName;dllPath=[IO.Path]::GetFullPath($binding.path);sha256=$SecurityDllSha256.ToLowerInvariant();policyPath=$policy;policySha256=(Get-HancomSecuritySha256 $policy).ToLowerInvariant();reviewConfirmed=$true}
    $null=Assert-HancomSecurityBinding ([pscustomobject]@{security=[pscustomobject]$security})
}
$environment=[ordered]@{
    schema='hangul.desktop-environment.v1';createdAt=(Get-Date).ToString('o');codexRoot=$CodexRoot
    pythonPath=if($python){$python.exe}else{$null};python=$python
    coreStatus=if($python){'ready'}elseif($basePython){'dependencies_missing'}else{'python_3_12_missing'}
    pdfCheckStatus=if($python -and $python.packages.PyMuPDF){'dependencies_present_not_render_verified'}else{'dependencies_missing'}
    legacyPdfTextCheckStatus=if($python -and $python.packages.pypdf){'dependency_present_not_extraction_verified'}else{'optional_pypdf_missing'}
    hancom=$hancom;security=$security
    nativeStatus=if($security.status -eq 'reviewed_existing'){'configured_not_runtime_verified'}else{'blocked_security_module'}
    registryChanges=@();dllsInstalled=@();executionPolicyChanged=$false
}
if($CheckOnly){$environment|ConvertTo-Json -Depth 14;exit 0}
$id='hangul-desktop-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
$bundle=Join-Path $CodexRoot ('skill-bundles/'+$id)
$backup=Join-Path $CodexRoot ('skill-backups/'+$id)
$skillsRoot=Join-Path $CodexRoot 'skills'
Assert-Child $bundle $CodexRoot;Assert-Child $backup $CodexRoot
foreach($name in @('hwpx','hwpx-windows-finalize')){Assert-Child (Join-Path $skillsRoot $name) $skillsRoot}
New-Item -ItemType Directory -Path (Split-Path $bundle),$backup,$skillsRoot -Force|Out-Null
Copy-Item -LiteralPath $source -Destination $bundle -Recurse
$environment.bundleRoot=$bundle;$environment.backupRoot=$backup
if($security.status -eq 'reviewed_existing'){
    $policyCopy=Join-Path $bundle 'reviewed-security-policy.txt'
    Copy-Item -LiteralPath $security.policyPath -Destination $policyCopy
    $security.policyPath=$policyCopy
}
$installed=@();$backedUp=@()
try{
    foreach($name in @('hwpx','hwpx-windows-finalize')){
        $target=Join-Path $skillsRoot $name
        if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination (Join-Path $backup $name);$backedUp+=$name}
        $installed+=$name
        Copy-Item -LiteralPath (Join-Path $bundle ('skills/'+$name)) -Destination $target -Recurse
        Write-Json $environment (Join-Path $target 'environment.json')
    }
    Write-Json $environment (Join-Path $bundle 'installed-environment.json')
    Write-Json @{status='installed';environment=$environment;restorableSkills=$backedUp;installedSkills=$installed} (Join-Path $backup 'installation-receipt.json')
}catch{
    $failure=$_.Exception.Message
    foreach($name in $installed){$target=Join-Path $skillsRoot $name;Assert-Child $target $skillsRoot;if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination (Join-Path $backup ('failed-new-'+$name))}}
    foreach($name in $backedUp){$saved=Join-Path $backup $name;Assert-Child $saved $backup;Move-Item -LiteralPath $saved -Destination (Join-Path $skillsRoot $name)}
    throw ('Installation rolled back: '+$failure)
}
$environment|ConvertTo-Json -Depth 14
Write-Output ('Skills installed. Backup: '+$backup)
if(!$python){Write-Warning 'Skills installed, but Python work is not ready. Install Python 3.12 or pass -PythonPath and rerun.'}
if($security.status -ne 'reviewed_existing'){Write-Warning 'Native COM document work remains blocked: no reviewed security module selected. No DLL or registry value was installed.'}

param([Parameter(Mandatory=$true)][string]$CodexRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'skills/hwpx-windows-finalize/scripts/Hancom.Environment.ps1')
if(!$env:PROCESSOR_ARCHITEW6432 -and $env:PROCESSOR_ARCHITECTURE -ne 'AMD64'){throw 'This bootstrap supports x64 Windows only.'}
$root=Join-Path $CodexRoot 'runtimes/hancom-bootstrap'
New-Item -ItemType Directory -Path $root -Force|Out-Null
$zip=Join-Path $root 'uv-0.12.22.zip'
if(!(Test-Path $zip)){Invoke-WebRequest -UseBasicParsing 'https://github.com/astral-sh/uv/releases/download/0.12.22/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip}
if((Get-HancomSecuritySha256 $zip) -ine 'ea1397797a0ca15f63516dd0f49c2dde9776db9be5861cab152ebe8ad199894d'){throw 'uv checksum mismatch'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$uvRoot=Join-Path $root 'uv'
if(!(Test-Path -LiteralPath $uvRoot)){
    [IO.Compression.ZipFile]::ExtractToDirectory($zip,$uvRoot)
}
$uv=(Get-ChildItem (Join-Path $root 'uv') -Filter uv.exe -Recurse|Select-Object -First 1).FullName
$archive=[IO.Compression.ZipFile]::OpenRead($zip)
try{
    $entries=@($archive.Entries | Where-Object {$_.Name -eq 'uv.exe'})
    if($entries.Count -ne 1){throw 'Expected exactly one uv.exe in pinned archive'}
    $stream=$entries[0].Open();$algorithm=[Security.Cryptography.SHA256]::Create()
    try{$expectedUv=([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-','')}
    finally{$stream.Dispose();$algorithm.Dispose()}
    if(!$uv -or (Get-HancomSecuritySha256 $uv) -ine $expectedUv){throw 'Extracted uv executable changed; no tool launched'}
}finally{$archive.Dispose()}
$old=$env:UV_PYTHON_INSTALL_DIR;$oldCache=$env:UV_CACHE_DIR
try{
 $env:UV_PYTHON_INSTALL_DIR=Join-Path $root 'python';$env:UV_CACHE_DIR=Join-Path $root 'cache'
 & $uv python install 3.12 --no-bin --no-registry --no-config
 if($LASTEXITCODE -ne 0){throw 'Managed Python download failed'}
 $python=& $uv python find 3.12 --managed-python
 if($LASTEXITCODE -ne 0){throw 'Managed Python not found'}
 [string]$python
}finally{$env:UV_PYTHON_INSTALL_DIR=$old;$env:UV_CACHE_DIR=$oldCache}

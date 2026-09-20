Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

$manifest = Get-Content 'build/build-manifest.json' -Raw | ConvertFrom-Json
$craftRoot = if ($env:CRAFT_ROOT) { $env:CRAFT_ROOT } else { 'C:\CraftRoot' }
$env:CRAFT_ROOT = $craftRoot

# Keep Git/MSYS and other bundled MinGW installations from shadowing the
# compiler/toolchain selected by KDE Craft.
$env:PATH = (($env:PATH -split ';') | Where-Object {
    $_ -and
    $_ -notmatch '(?i)\\Git\\bin$' -and
    $_ -notmatch '(?i)\\Git\\usr\\bin$' -and
    $_ -notmatch '(?i)\\mingw64\\bin$' -and
    $_ -notmatch '(?i)\\Strawberry\\c\\bin$'
}) -join ';'

New-Item -ItemType Directory -Force (Join-Path $craftRoot 'download') | Out-Null
$bootstrap = Join-Path $craftRoot 'download\CraftBootstrap.py'

Write-Host "Craft revision: $($manifest.craft.revision)"
Invoke-WebRequest $manifest.craft.bootstrap_url -OutFile $bootstrap

python scripts/patch_craft_bootstrap.py $bootstrap
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python $bootstrap --prefix $craftRoot --branch $manifest.craft.revision --use-defaults
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$cfg = Join-Path $craftRoot 'etc\CraftSettings.ini'
if (-not (Test-Path $cfg)) {
    throw "Craft settings not found: $cfg"
}

python scripts/configure_craft.py $cfg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Get-Content $cfg | Select-String 'ABI|BuildType|UseNinja|MakeProgram|ShortPath|DriveLetter|UseCache'

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $env:CRAFT_ROOT) {
    throw 'CRAFT_ROOT is not configured.'
}

$locations = Join-Path $env:CRAFT_ROOT 'etc\blueprints\locations'
$blueprintRoot = Get-ChildItem $locations -Directory -Filter 'craft-blueprints-kde' -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $blueprintRoot) {
    throw "Could not locate the KDE Craft blueprint root below $locations."
}

$target = Join-Path $blueprintRoot.FullName 'kde\kdemultimedia\editaja'
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item 'craft/editaja/*' $target -Recurse -Force

Write-Host "Update P5 Edit Aja blueprint: $target"
Get-ChildItem $target

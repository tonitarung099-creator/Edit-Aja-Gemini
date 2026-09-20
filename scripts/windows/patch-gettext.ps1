Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

if (-not $env:CRAFT_ROOT) {
    throw 'CRAFT_ROOT is not configured.'
}

$gettextBlueprint = Join-Path $env:CRAFT_ROOT 'craft\blueprints\libs\gettext\gettext.py'
if (-not (Test-Path $gettextBlueprint)) {
    throw "Craft gettext blueprint not found: $gettextBlueprint"
}

python scripts/patch_gettext_blueprint.py $gettextBlueprint
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Select-String -Path $gettextBlueprint -Pattern 'LIBS=-lxml2' -Quiet)) {
    throw 'gettext MinGW libxml2 hotfix verification failed.'
}

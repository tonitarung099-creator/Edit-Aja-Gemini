param([switch]$DependenciesOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

. "$PSScriptRoot\craft-env.ps1"

[void](Enter-CraftEnvironment)

$arguments = @('--craft-root', $env:CRAFT_ROOT, '--package', 'kde/kdemultimedia/editaja')
if ($DependenciesOnly) { $arguments += '--dependencies-only' }
python "$PSScriptRoot\..\prepare_package_images.py" @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

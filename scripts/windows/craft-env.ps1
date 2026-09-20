Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Enter-CraftEnvironment {
    [CmdletBinding()]
    param(
        [string]$CraftRoot = $env:CRAFT_ROOT
    )

    if ([string]::IsNullOrWhiteSpace($CraftRoot)) {
        throw 'CRAFT_ROOT is not configured.'
    }

    $helper = Join-Path $CraftRoot 'craft\bin\CraftSetupHelper.py'
    if (-not (Test-Path $helper)) {
        throw "Craft setup helper not found: $helper"
    }

    $setup = ConvertFrom-Json (& python $helper --setup --format=json)
    if ($LASTEXITCODE -ne 0) {
        throw "Craft environment setup failed with exit code $LASTEXITCODE."
    }

    foreach ($property in $setup.PSObject.Properties) {
        Set-Item -Force -Path "Env:$($property.Name)" -Value "$($property.Value)"
    }

    $craft = Join-Path $CraftRoot 'craft\bin\craft.py'
    if (-not (Test-Path $craft)) {
        throw "Craft executable not found: $craft"
    }

    return $craft
}

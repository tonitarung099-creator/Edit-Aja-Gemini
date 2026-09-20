Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\craft-env.ps1"

if (-not $env:CRAFT_BUILD_TYPE) {
    $env:CRAFT_BUILD_TYPE = 'RelWithDebInfo'
}

New-Item -ItemType Directory -Force 'artifacts/windows' | Out-Null
$binaryCount = 0
$craft = Enter-CraftEnvironment

# packageDestinationDir() is a convenience query. If Craft changes the query
# interface, the fallback search below still finds a successfully built package.
$previousNativePreference = $PSNativeCommandUseErrorActionPreference
$PSNativeCommandUseErrorActionPreference = $false
$packageDirOutput = & python $craft --ci-mode --buildtype $env:CRAFT_BUILD_TYPE -q --get 'packageDestinationDir()' virtual/base 2>$null
$queryExitCode = $LASTEXITCODE
$PSNativeCommandUseErrorActionPreference = $previousNativePreference

$packageDir = ''
if ($queryExitCode -eq 0 -and $packageDirOutput) {
    $packageDir = "$($packageDirOutput | Select-Object -Last 1)".Trim()
}

if ($packageDir -and (Test-Path $packageDir)) {
    Write-Host "Craft package directory: $packageDir"
    $packages = Get-ChildItem $packageDir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -in '.exe', '.zip', '.7z', '.sha256' -and
            ($_.Name -match 'edit.?aja' -or $_.Name -match 'editaja')
        }

    foreach ($item in $packages) {
        Copy-Item $item.FullName (Join-Path 'artifacts/windows' $item.Name) -Force
        if ($item.Extension -in '.exe', '.zip', '.7z') {
            $binaryCount++
        }
    }
}

if ($binaryCount -eq 0 -and (Test-Path $env:CRAFT_ROOT)) {
    Write-Host 'Craft package directory query produced no runnable package; using fallback search.'
    $packages = Get-ChildItem $env:CRAFT_ROOT -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension -in '.exe', '.zip', '.7z' -and
            ($_.Name -match 'edit.?aja' -or $_.Name -match 'editaja')
        } |
        Select-Object -First 10

    foreach ($item in $packages) {
        Copy-Item $item.FullName (Join-Path 'artifacts/windows' $item.Name) -Force
        $binaryCount++
    }
}

Get-ChildItem 'artifacts/windows' -File | Format-Table Name, Length

if ($binaryCount -eq 0) {
    throw 'No runnable Update P5 Edit Aja Windows package was produced.'
}

$global:LASTEXITCODE = 0

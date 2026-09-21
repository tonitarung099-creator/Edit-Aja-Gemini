Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\craft-env.ps1"

if (-not $env:CRAFT_BUILD_TYPE) {
    $env:CRAFT_BUILD_TYPE = 'RelWithDebInfo'
}

$artifactRoot = Join-Path (Get-Location) 'artifacts/windows'
New-Item -ItemType Directory -Force $artifactRoot | Out-Null
Get-ChildItem $artifactRoot -File -ErrorAction SilentlyContinue | Remove-Item -Force

$craft = Enter-CraftEnvironment

# Query Craft's package output first. The fallback search is only for resilience
# if the query interface changes in the pinned Craft revision.
$previousNativePreference = $PSNativeCommandUseErrorActionPreference
$PSNativeCommandUseErrorActionPreference = $false
$packageDirOutput = & python $craft --ci-mode --buildtype $env:CRAFT_BUILD_TYPE -q --get 'packageDestinationDir()' virtual/base 2>$null
$queryExitCode = $LASTEXITCODE
$PSNativeCommandUseErrorActionPreference = $previousNativePreference

$packageDir = ''
if ($queryExitCode -eq 0 -and $packageDirOutput) {
    $packageDir = "$($packageDirOutput | Select-Object -Last 1)".Trim()
}

$candidates = @()
if ($packageDir -and (Test-Path $packageDir)) {
    Write-Host "Craft package directory: $packageDir"
    $candidates = @(
        Get-ChildItem $packageDir -Recurse -File -Filter '*.zip' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'edit.?aja' } |
            Sort-Object Length -Descending
    )
}

if ($candidates.Count -eq 0 -and (Test-Path $env:CRAFT_ROOT)) {
    Write-Host 'Craft package directory query produced no portable ZIP; using fallback search.'
    $candidates = @(
        Get-ChildItem $env:CRAFT_ROOT -Recurse -File -Filter '*.zip' -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match 'edit.?aja' } |
            Sort-Object Length -Descending |
            Select-Object -First 10
    )
}

if ($candidates.Count -eq 0) {
    throw 'No Edit Aja Gemini portable ZIP package was produced.'
}

$source = $candidates[0]
$destination = Join-Path $artifactRoot 'Edit-Aja-Gemini-Windows-Portable-x64.zip'
Copy-Item $source.FullName $destination -Force

$hash = (Get-FileHash $destination -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $(Split-Path $destination -Leaf)" | Set-Content -Path "$destination.sha256" -Encoding ascii

if (Get-ChildItem $artifactRoot -File -Filter '*.exe' -ErrorAction SilentlyContinue) {
    throw 'Portable artifact directory must not contain an installer EXE.'
}

Get-ChildItem $artifactRoot -File | Format-Table Name, Length
Write-Host "Portable package collected: $destination"
$global:LASTEXITCODE = 0

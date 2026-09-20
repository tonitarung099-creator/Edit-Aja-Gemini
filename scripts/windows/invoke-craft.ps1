param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install-deps', 'build', 'install-packager', 'package')]
    [string]$Mode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

. "$PSScriptRoot\craft-env.ps1"

if (-not $env:CRAFT_BUILD_TYPE) {
    $env:CRAFT_BUILD_TYPE = 'RelWithDebInfo'
}

$craft = Enter-CraftEnvironment
$package = 'kde/kdemultimedia/editaja'

switch ($Mode) {
    'install-deps' {
        $arguments = @('--ci-mode', '--buildtype', $env:CRAFT_BUILD_TYPE, '--use-cache', '--install-deps', $package)
        # KDE's binary/source mirrors occasionally return transient connection
        # errors. Craft keeps completed packages installed, so retrying the same
        # dependency command resumes from the remaining package set.
        $maxAttempts = 3
    }
    'build' {
        # Dependencies may use KDE's binary cache, but the modified application
        # itself must always be compiled from our prepared source.
        $arguments = @('--ci-mode', '--buildtype', $env:CRAFT_BUILD_TYPE, '--no-cache', $package)
        $maxAttempts = 1
    }
    'install-packager' {
        $arguments = @('--ci-mode', '--buildtype', $env:CRAFT_BUILD_TYPE, '--use-cache', '--update', 'nsis')
        $maxAttempts = 1
    }
    'package' {
        $arguments = @('--ci-mode', '--buildtype', $env:CRAFT_BUILD_TYPE, '--package', $package)
        $maxAttempts = 1
    }
}

Write-Host "Craft mode: $Mode"

$exitCode = 1
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    if ($maxAttempts -gt 1) {
        Write-Host "Craft dependency attempt $attempt/$maxAttempts"
    }

    # We need the native exit code so a transient network failure can be retried
    # rather than converted into a terminating PowerShell exception immediately.
    $nativeErrorsWereFatal = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        python $craft @arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $PSNativeCommandUseErrorActionPreference = $nativeErrorsWereFatal
    }

    if ($exitCode -eq 0) {
        exit 0
    }

    if ($attempt -lt $maxAttempts) {
        $delaySeconds = 20 * $attempt
        Write-Warning "Craft dependency installation failed with exit code $exitCode. Retrying in $delaySeconds seconds; already-installed packages will be reused."
        Start-Sleep -Seconds $delaySeconds
    }
}

exit $exitCode

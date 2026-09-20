Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. "$PSScriptRoot\smoke-test-support.ps1"

$packageRoot = Join-Path (Get-Location) 'artifacts/windows'
if (-not (Test-Path $packageRoot)) {
    throw "Windows package directory not found: $packageRoot"
}

$installers = @(
    Get-ChildItem $packageRoot -File -Filter '*.exe' |
        Where-Object { $_.Name -match 'edit.?aja' } |
        Sort-Object Length -Descending
)
if ($installers.Count -eq 0) {
    throw 'No Edit Aja NSIS installer was found in artifacts/windows.'
}

# Craft can emit companion package files. Prefer the largest matching EXE,
# which is the NSIS installer containing the application payload.
$installer = $installers[0]
$requestedInstallRoot = Join-Path $env:RUNNER_TEMP 'editaja-packaged-app-smoke'
$installRegistryPath = 'HKCU:\Software\KDE e.V.\Update P5 Edit Aja'
$stdout = Join-Path $env:RUNNER_TEMP 'editaja-version-stdout.txt'
$stderr = Join-Path $env:RUNNER_TEMP 'editaja-version-stderr.txt'

if (Test-Path $requestedInstallRoot) {
    Remove-Item $requestedInstallRoot -Recurse -Force
}
Remove-Item $stdout, $stderr -Force -ErrorAction SilentlyContinue

$diagnostics = Join-Path (Get-Location) 'artifacts/smoke/startup'
$appStdout = Join-Path $env:RUNNER_TEMP 'editaja-startup-stdout.txt'
$appStderr = Join-Path $env:RUNNER_TEMP 'editaja-startup-stderr.txt'
$stage = 'install'
$status = 'FAIL'
Remove-Item $appStdout, $appStderr -Force -ErrorAction SilentlyContinue

$appProcess = $null
$installedRoot = $null

function Resolve-InstalledRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RegistryPath
    )

    if (-not (Test-Path -LiteralPath $RegistryPath)) {
        throw "Installer completed but its CurrentUser registry key was not created: $RegistryPath"
    }

    $properties = Get-ItemProperty -LiteralPath $RegistryPath
    $root = "$($properties.Install_Dir)".Trim()
    if (-not $root) {
        throw "Installer registry key exists but Install_Dir is empty: $RegistryPath"
    }

    return $root
}

try {
    Write-Host "Smoke installer: $($installer.FullName)"
    Write-Host "Requested smoke install root: $requestedInstallRoot"

    # The pinned Craft NSIS template enables MULTIUSER_INSTALLMODE_COMMANDLINE.
    # /CurrentUser avoids an elevation requirement in the hosted runner.
    # MultiUser initialization owns the final $INSTDIR, so after installation
    # the smoke test reads Craft's authoritative Install_Dir registry value
    # instead of assuming the requested /D path survived initialization.
    $install = Start-Process -FilePath $installer.FullName -ArgumentList @('/S', '/CurrentUser', "/D=$requestedInstallRoot") -PassThru -Wait
    if ($install.ExitCode -ne 0) {
        throw "Silent installer exited with code $($install.ExitCode)."
    }

    $installedRoot = Resolve-InstalledRoot -RegistryPath $installRegistryPath
    Write-Host "Registered install root: $installedRoot"

    $app = Join-Path $installedRoot 'bin/kdenlive.exe'
    $uninstaller = Join-Path $installedRoot 'uninstall.exe'
    if (-not (Test-Path $app -PathType Leaf)) {
        throw "Installed application executable not found at registered install root: $app"
    }
    if (-not (Test-Path $uninstaller -PathType Leaf)) {
        throw "Installed uninstaller not found at registered install root: $uninstaller"
    }

    Write-Host 'Installer PASS: packaged application files are present at the registered install root.'

    # --version initializes the packaged executable and its DLL search path, but
    # exits without requiring GUI interaction. Missing runtime DLLs surface here
    # as a non-zero process exit instead of being mistaken for packaging success.
    $stage = 'version'
    $version = Start-Process -FilePath $app -ArgumentList @('--version') -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru

    if (-not $version.WaitForExit(30000)) {
        Stop-SmokeProcessTree -Process $version
        throw 'Packaged application --version did not exit within 30 seconds.'
    }

    $versionOut = if (Test-Path $stdout) { Get-Content $stdout -Raw } else { '' }
    $versionErr = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { '' }
    if ($version.ExitCode -ne 0) {
        throw "Packaged application --version failed with code $($version.ExitCode).\nSTDOUT:\n$versionOut\nSTDERR:\n$versionErr"
    }
    Write-Host "Executable probe PASS. Output: $($versionOut.Trim())"

    # A successful version probe is not enough to prove GUI startup. Launch the
    # packaged application normally and require it to remain alive long enough
    # to rule out an immediate startup/runtime crash.
    $stage = 'startup'
    $appProcess = Start-Process -FilePath $app -RedirectStandardOutput $appStdout -RedirectStandardError $appStderr -PassThru
    for ($second = 0; $second -lt 15; $second++) {
        Start-Sleep -Seconds 1
        Assert-SmokeProcessRunning -Process $appProcess -Stage $stage
    }
    $status = 'PASS'

    Write-Host 'Packaged-app startup smoke PASS: process remained alive for 15 seconds.'
}
finally {
    Stop-SmokeProcessTree -Process $appProcess
    try {
        Export-SmokeDiagnostics -Directory $diagnostics -Stage $stage -Status $status -LogPaths @($stdout, $stderr, $appStdout, $appStderr) -DiscoveryFile (Join-Path $env:TEMP 'kdenlive-open-agent.json')
    }
    catch { Write-Warning "Could not save smoke diagnostics: $($_.Exception.Message)" }

    if ($installedRoot) {
        $uninstaller = Join-Path $installedRoot 'uninstall.exe'
        if (Test-Path $uninstaller -PathType Leaf) {
            Write-Host "Running silent smoke-test uninstall from: $installedRoot"
            $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @('/S', "_?=$installedRoot") -PassThru -Wait
            if ($uninstall.ExitCode -ne 0) {
                Write-Warning "Smoke-test uninstaller exited with code $($uninstall.ExitCode)."
            }
        }
    }

    foreach ($root in @($installedRoot, $requestedInstallRoot)) {
        if ($root -and (Test-Path $root)) {
            Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

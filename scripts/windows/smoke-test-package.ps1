Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. "$PSScriptRoot\smoke-test-support.ps1"

$packageRoot = Join-Path (Get-Location) 'artifacts/windows'
$portableZip = Join-Path $packageRoot 'Edit-Aja-Gemini-Windows-Portable-x64.zip'
if (-not (Test-Path $portableZip -PathType Leaf)) {
    throw "Portable Windows ZIP not found: $portableZip"
}

$portableRoot = Join-Path $env:RUNNER_TEMP 'editaja-portable-startup-smoke'
$stdout = Join-Path $env:RUNNER_TEMP 'editaja-version-stdout.txt'
$stderr = Join-Path $env:RUNNER_TEMP 'editaja-version-stderr.txt'
$appStdout = Join-Path $env:RUNNER_TEMP 'editaja-startup-stdout.txt'
$appStderr = Join-Path $env:RUNNER_TEMP 'editaja-startup-stderr.txt'
$diagnostics = Join-Path (Get-Location) 'artifacts/smoke/startup'
$stage = 'extract'
$status = 'FAIL'
$appProcess = $null

foreach ($path in @($portableRoot, $stdout, $stderr, $appStdout, $appStderr)) {
    Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
}

try {
    Expand-Archive -LiteralPath $portableZip -DestinationPath $portableRoot -Force

    $apps = @(
        Get-ChildItem $portableRoot -Recurse -File -Filter 'kdenlive.exe' |
            Where-Object { $_.FullName -match '[\\/]bin[\\/]kdenlive\.exe$' }
    )
    if ($apps.Count -ne 1) {
        throw "Expected exactly one portable bin/kdenlive.exe, found $($apps.Count)."
    }
    $app = $apps[0].FullName
    Write-Host "Portable app: $app"

    $stage = 'version'
    $version = Start-Process -FilePath $app -ArgumentList @('--version') -WorkingDirectory (Split-Path $app -Parent) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    if (-not $version.WaitForExit(30000)) {
        Stop-SmokeProcessTree -Process $version
        throw 'Portable application --version did not exit within 30 seconds.'
    }

    $versionOut = if (Test-Path $stdout) { Get-Content $stdout -Raw } else { '' }
    $versionErr = if (Test-Path $stderr) { Get-Content $stderr -Raw } else { '' }
    if ($version.ExitCode -ne 0) {
        throw "Portable application --version failed with code $($version.ExitCode).\nSTDOUT:\n$versionOut\nSTDERR:\n$versionErr"
    }
    Write-Host "Portable executable probe PASS. Output: $($versionOut.Trim())"

    $stage = 'startup'
    $appProcess = Start-Process -FilePath $app -WorkingDirectory (Split-Path $app -Parent) -RedirectStandardOutput $appStdout -RedirectStandardError $appStderr -PassThru
    for ($second = 0; $second -lt 15; $second++) {
        Start-Sleep -Seconds 1
        Assert-SmokeProcessRunning -Process $appProcess -Stage $stage
    }
    $status = 'PASS'
    Write-Host 'Portable-app startup smoke PASS: process remained alive for 15 seconds without installation.'
}
finally {
    Stop-SmokeProcessTree -Process $appProcess
    try {
        Export-SmokeDiagnostics -Directory $diagnostics -Stage $stage -Status $status -LogPaths @($stdout, $stderr, $appStdout, $appStderr) -DiscoveryFile (Join-Path $env:TEMP 'kdenlive-open-agent.json')
    }
    catch { Write-Warning "Could not save smoke diagnostics: $($_.Exception.Message)" }

    if (Test-Path $portableRoot) {
        Remove-Item $portableRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

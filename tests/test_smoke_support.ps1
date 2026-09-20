Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. "$PSScriptRoot\..\scripts\windows\smoke-test-support.ps1"

$root = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory $root | Out-Null
try {
    Assert-SmokeProcessRunning -Process (Get-Process -Id $PID) -Stage 'running fixture'
    $pwsh = (Get-Process -Id $PID).Path
    $exited = Start-Process -FilePath $pwsh -ArgumentList @('-NoProfile', '-Command', 'exit 7') -PassThru -Wait
    $rejected = $false
    try { Assert-SmokeProcessRunning -Process $exited -Stage 'bridge' }
    catch {
        $rejected = $_.Exception.Message -like '*bridge*code 7*'
    }
    if (-not $rejected) { throw 'Exited application was not rejected with its stage and exit code.' }
    # Already-exited process cleanup must preserve the original failure.
    Stop-SmokeProcessTree -Process $exited

    $token = 'fixture-secret-73'
    $discovery = Join-Path $root 'discovery.json'
    @{ token = $token } | ConvertTo-Json | Set-Content $discovery
    $log = Join-Path $root 'stderr.txt'
    "useful error; token=$token; Authorization: Bearer other-secret-42" | Set-Content $log
    $destination = Join-Path $root 'diagnostics'
    Export-SmokeDiagnostics -Directory $destination -Stage 'subtitle_edit' -Status 'FAIL' -LogPaths @($log, (Join-Path $root 'missing.txt')) -DiscoveryFile $discovery
    $saved = Get-Content (Join-Path $destination 'stderr.txt') -Raw
    if ($saved.Contains($token) -or $saved.Contains('other-secret-42') -or -not $saved.Contains('useful error')) {
        throw 'Diagnostics did not preserve evidence while redacting credentials.'
    }
    if (Test-Path (Join-Path $destination 'discovery.json')) { throw 'Discovery credentials were copied.' }
    $result = Get-Content (Join-Path $destination 'result.json') -Raw | ConvertFrom-Json
    if ($result.status -ne 'FAIL' -or $result.stage -ne 'subtitle_edit' -or $result.commit -ne (& git rev-parse HEAD).Trim()) {
        throw 'Diagnostics did not retain the failed stage and checked-out commit.'
    }

    # A GUI application often produces no stdout. Exercise a genuinely empty
    # redirected file with a live discovery token, as in the packaged smoke.
    $emptyLog = Join-Path $root 'empty-stdout.txt'
    [System.IO.File]::WriteAllBytes($emptyLog, [byte[]]@())
    $emptyDestination = Join-Path $root 'empty-output'
    Export-SmokeDiagnostics -Directory $emptyDestination -Stage 'save_copy' -Status 'PASS' -LogPaths @($emptyLog, $log) -DiscoveryFile $discovery
    if (-not (Test-Path (Join-Path $emptyDestination 'result.json'))) { throw 'An empty log lost the stage report.' }
    if (-not (Test-Path (Join-Path $emptyDestination 'stderr.txt'))) { throw 'An empty stdout prevented stderr export.' }
    $emptyResult = Get-Content (Join-Path $emptyDestination 'result.json') -Raw | ConvertFrom-Json
    if ($emptyResult.status -ne 'PASS' -or $emptyResult.stage -ne 'save_copy') { throw 'Empty output changed the recorded test result.' }
    $emptySaved = [System.IO.File]::ReadAllText((Join-Path $emptyDestination 'empty-stdout.txt'))
    if ($emptySaved.Trim().Length -ne 0) { throw 'Empty stdout acquired unexpected content.' }
    $stderrSaved = Get-Content (Join-Path $emptyDestination 'stderr.txt') -Raw
    if ($stderrSaved.Contains($token) -or $stderrSaved.Contains('other-secret-42') -or -not $stderrSaved.Contains('useful error')) {
        throw 'Redaction or stderr evidence failed after empty stdout.'
    }

    'malformed secret discovery' | Set-Content $discovery
    $badDestination = Join-Path $root 'malformed-discovery'
    Export-SmokeDiagnostics -Directory $badDestination -Stage 'bridge' -Status 'FAIL' -LogPaths @($log) -DiscoveryFile $discovery
    if (Test-Path (Join-Path $badDestination 'stderr.txt')) { throw 'Unredacted logs were exported with malformed discovery data.' }
    if (-not (Test-Path (Join-Path $badDestination 'result.json'))) { throw 'Failure-stage report is missing.' }
    Write-Host 'Smoke support tests PASS: process exit, cleanup, stage evidence, redaction, empty/missing logs, malformed discovery.'
}
finally { Remove-Item $root -Recurse -Force }

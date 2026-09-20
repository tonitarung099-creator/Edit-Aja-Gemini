Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
. "$PSScriptRoot\smoke-test-support.ps1"

$packageRoot = Join-Path (Get-Location) 'artifacts/windows'
$fixtureSource = Join-Path (Get-Location) 'corresponding-source/tests/dataset/av.kdenlive'
if (-not (Test-Path $packageRoot)) {
    throw "Windows package directory not found: $packageRoot"
}
if (-not (Test-Path $fixtureSource -PathType Leaf)) {
    throw "Functional smoke project fixture not found: $fixtureSource"
}

$installers = @(
    Get-ChildItem $packageRoot -File -Filter '*.exe' |
        Where-Object { $_.Name -match 'edit.?aja' } |
        Sort-Object Length -Descending
)
if ($installers.Count -eq 0) {
    throw 'No Edit Aja NSIS installer was found in artifacts/windows.'
}

$installer = $installers[0]
$requestedInstallRoot = Join-Path $env:RUNNER_TEMP 'editaja-functional-smoke-install'
$installRegistryPath = 'HKCU:\Software\KDE e.V.\Update P5 Edit Aja'
$workRoot = Join-Path $env:RUNNER_TEMP 'editaja-functional-smoke'
$projectPath = Join-Path $workRoot 'input.kdenlive'
$savedProjectPath = Join-Path $workRoot 'saved-copy.kdenlive'
$discoveryPath = Join-Path $env:TEMP 'kdenlive-open-agent.json'

$diagnostics = Join-Path (Get-Location) 'artifacts/smoke/functional'
$appStdout = Join-Path $env:RUNNER_TEMP 'editaja-functional-stdout.txt'
$appStderr = Join-Path $env:RUNNER_TEMP 'editaja-functional-stderr.txt'
$stage = 'install'
$status = 'FAIL'
Remove-Item $appStdout, $appStderr -Force -ErrorAction SilentlyContinue

$appProcess = $null
$installedRoot = $null

function Resolve-InstalledRoot {
    if (-not (Test-Path -LiteralPath $installRegistryPath)) {
        throw "Installer completed but CurrentUser registry key is missing: $installRegistryPath"
    }
    $root = "$((Get-ItemProperty -LiteralPath $installRegistryPath).Install_Dir)".Trim()
    if (-not $root) {
        throw "Installer registry key exists but Install_Dir is empty: $installRegistryPath"
    }
    return $root
}

function Invoke-AgentGet {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Token
    )
    return Invoke-RestMethod -Method Get -Uri $Url -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 20
}

function Invoke-AgentTool {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][string]$Name,
        [hashtable]$Arguments = @{},
        [int]$TimeoutSeconds = 30
    )

    $body = @{ name = $Name; arguments = $Arguments } | ConvertTo-Json -Depth 20 -Compress
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host "Native tool call: $Name (timeout ${TimeoutSeconds}s)"
    try {
        $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/tools/call" -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json' -Body $body -TimeoutSec $TimeoutSeconds
    }
    catch {
        $timer.Stop()
        throw "Native tool '$Name' HTTP call failed after $([Math]::Round($timer.Elapsed.TotalSeconds, 1))s: $($_.Exception.Message)"
    }
    $timer.Stop()
    Write-Host "Native tool call complete: $Name in $([Math]::Round($timer.Elapsed.TotalSeconds, 1))s."

    if (-not $response.ok) {
        throw "REST wrapper rejected tool '$Name': $($response | ConvertTo-Json -Depth 20 -Compress)"
    }

    $result = $response.result
    if ($null -eq $result) {
        throw "Tool '$Name' returned no result."
    }

    if (($result.PSObject.Properties.Name -contains 'ok') -and -not $result.ok) {
        throw "Tool '$Name' failed: $($result | ConvertTo-Json -Depth 20 -Compress)"
    }

    return $result
}

function Wait-AgentBridge {
    param(
        [Parameter(Mandatory = $true)][string]$DiscoveryFile,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null

    while ((Get-Date) -lt $deadline) {
        Assert-SmokeProcessRunning -Process $appProcess -Stage $stage
        if (Test-Path $DiscoveryFile -PathType Leaf) {
            try {
                $discovery = Get-Content $DiscoveryFile -Raw | ConvertFrom-Json
                if ($discovery.rest_base_url -and $discovery.token) {
                    $ping = Invoke-AgentGet -Url "$($discovery.rest_base_url)/ping" -Token $discovery.token
                    if ($ping.ok -and $ping.result -eq 'pong') {
                        return $discovery
                    }
                }
            }
            catch {
                $lastError = $_
            }
        }
        Start-Sleep -Milliseconds 500
    }

    if ($lastError) {
        throw "AI/REST bridge did not become ready within $TimeoutSeconds seconds. Last error: $lastError"
    }
    throw "AI/REST bridge discovery file did not become ready within $TimeoutSeconds seconds: $DiscoveryFile"
}

function Wait-ProjectLoaded {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [int]$TimeoutSeconds = 60
    )

    $expected = [System.IO.Path]::GetFullPath($ExpectedPath)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $last = $null

    while ((Get-Date) -lt $deadline) {
        Assert-SmokeProcessRunning -Process $appProcess -Stage $stage
        try {
            $last = Invoke-AgentTool -BaseUrl $BaseUrl -Token $Token -Name 'kdenlive_get_project_info'
            if ($last.path) {
                $actual = [System.IO.Path]::GetFullPath("$($last.path)")
                if ($actual.Equals($expected, [System.StringComparison]::OrdinalIgnoreCase) -and [int]$last.duration_frames -gt 0) {
                    return $last
                }
            }
        }
        catch {
            $last = $_
        }
        Start-Sleep -Milliseconds 750
    }

    throw "Project did not become ready in the native tool registry. Last state: $($last | Out-String)"
}

try {
    foreach ($path in @($requestedInstallRoot, $workRoot)) {
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
        }
    }
    New-Item -ItemType Directory -Force $workRoot | Out-Null
    Copy-Item $fixtureSource $projectPath -Force
    Remove-Item $discoveryPath -Force -ErrorAction SilentlyContinue

    Write-Host "Functional smoke installer: $($installer.FullName)"
    $install = Start-Process -FilePath $installer.FullName -ArgumentList @('/S', '/CurrentUser', "/D=$requestedInstallRoot") -PassThru -Wait
    if ($install.ExitCode -ne 0) {
        throw "Silent installer exited with code $($install.ExitCode)."
    }

    $installedRoot = Resolve-InstalledRoot
    $app = Join-Path $installedRoot 'bin/kdenlive.exe'
    if (-not (Test-Path $app -PathType Leaf)) {
        throw "Installed application executable not found: $app"
    }

    Write-Host "Launching packaged editor with functional project: $projectPath"
    $quotedProject = '"' + $projectPath + '"'
    $stage = 'launch'
    $appProcess = Start-Process -FilePath $app -ArgumentList @($quotedProject) -RedirectStandardOutput $appStdout -RedirectStandardError $appStderr -PassThru

    $stage = 'bridge'
    $discovery = Wait-AgentBridge -DiscoveryFile $discoveryPath
    $baseUrl = "$($discovery.rest_base_url)"
    $token = "$($discovery.token)"
    Write-Host "REST bridge PASS: $baseUrl"

    $stage = 'tool_catalog'
    $catalog = Invoke-AgentGet -Url "$baseUrl/tools" -Token $token
    $toolNames = @($catalog.tools | ForEach-Object { "$($_.name)" })
    $requiredTools = @(
        'kdenlive_get_project_info',
        'kdenlive_get_timeline_state',
        'kdenlive_cut_clip',
        'kdenlive_add_subtitle',
        'kdenlive_list_subtitles',
        'kdenlive_save_project'
    )
    foreach ($required in $requiredTools) {
        if ($toolNames -notcontains $required) {
            throw "Native tool catalog is missing required functional-smoke tool: $required"
        }
    }
    Write-Host "Native tool catalog PASS: $($requiredTools.Count) required tools are present."

    $stage = 'project_load'
    $project = Wait-ProjectLoaded -BaseUrl $baseUrl -Token $token -ExpectedPath $projectPath
    Write-Host "Project load PASS: $($project.path), duration=$($project.duration_frames) frames."

    $stage = 'timeline_split'
    $before = Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_get_timeline_state' -Arguments @{ include_items = $true }
    $clipsBefore = @($before.items | Where-Object { $_.kind -eq 'clip' -and [int]$_.duration_frames -ge 4 })
    if ($clipsBefore.Count -eq 0) {
        throw "Functional smoke project has no editable timeline clips: $($before | ConvertTo-Json -Depth 20 -Compress)"
    }

    $clip = $clipsBefore | Sort-Object @{ Expression = { [int]$_.duration_frames }; Descending = $true } | Select-Object -First 1
    $cutFrame = [int]$clip.position_frame + [Math]::Floor([int]$clip.duration_frames / 2)
    if ($cutFrame -le [int]$clip.position_frame -or $cutFrame -ge [int]$clip.end_frame) {
        throw "Could not choose a valid cut frame for clip $($clip.id)."
    }

    [void](Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_cut_clip' -Arguments @{ clip_id = [int]$clip.id; position_frame = $cutFrame })

    $afterCut = Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_get_timeline_state' -Arguments @{ include_items = $true }
    $clipCountBefore = @($before.items | Where-Object { $_.kind -eq 'clip' }).Count
    $clipCountAfter = @($afterCut.items | Where-Object { $_.kind -eq 'clip' }).Count
    if ($clipCountAfter -le $clipCountBefore) {
        throw "Timeline cut did not increase clip count. Before=$clipCountBefore After=$clipCountAfter"
    }
    Write-Host "Timeline split PASS: clips $clipCountBefore -> $clipCountAfter."

    $stage = 'subtitle_edit'
    $subtitleText = 'P5 functional smoke subtitle'
    [void](Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_add_subtitle' -Arguments @{ text = $subtitleText; start_seconds = 1.0; duration_seconds = 1.5; layer = 0 })

    $subtitles = Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_list_subtitles'
    $matchingSubtitle = @($subtitles.subtitles | Where-Object { $_.text -eq $subtitleText })
    if ($matchingSubtitle.Count -ne 1) {
        throw "Subtitle add/list verification failed: $($subtitles | ConvertTo-Json -Depth 20 -Compress)"
    }
    Write-Host 'Subtitle native edit PASS.'

    $stage = 'save_copy'
    # Keep the save-specific timeout while checking that the requested file is
    # actually written. A longer timeout alone does not prove a successful save.
    [void](Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_save_project' -Arguments @{ path = $savedProjectPath; save_copy = $true; overwrite = $true } -TimeoutSeconds 120)
    if (-not (Test-Path $savedProjectPath -PathType Leaf)) {
        throw "Native save tool reported success but project copy was not created: $savedProjectPath"
    }
    if ((Get-Item $savedProjectPath).Length -lt 1024) {
        throw "Saved project copy is unexpectedly small: $((Get-Item $savedProjectPath).Length) bytes"
    }

    $projectAfterSave = Invoke-AgentTool -BaseUrl $baseUrl -Token $token -Name 'kdenlive_get_project_info'
    $currentPath = [System.IO.Path]::GetFullPath("$($projectAfterSave.path)")
    $originalPath = [System.IO.Path]::GetFullPath($projectPath)
    if (-not $currentPath.Equals($originalPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "save_copy changed the active project path unexpectedly: $currentPath"
    }

    Write-Host "Project save-copy PASS: $savedProjectPath"
    $status = 'PASS'
    Write-Host 'FUNCTIONAL EDITOR SMOKE PASS: REST/native registry, project load, timeline split, subtitle edit, and project save-copy.'
}
finally {
    Stop-SmokeProcessTree -Process $appProcess
    try {
        Export-SmokeDiagnostics -Directory $diagnostics -Stage $stage -Status $status -LogPaths @($appStdout, $appStderr) -DiscoveryFile $discoveryPath
    }
    catch { Write-Warning "Could not save smoke diagnostics: $($_.Exception.Message)" }

    if ($installedRoot) {
        $uninstaller = Join-Path $installedRoot 'uninstall.exe'
        if (Test-Path $uninstaller -PathType Leaf) {
            Write-Host "Functional smoke uninstall: $installedRoot"
            $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @('/S', "_?=$installedRoot") -PassThru -Wait
            if ($uninstall.ExitCode -ne 0) {
                Write-Warning "Functional-smoke uninstaller exited with code $($uninstall.ExitCode)."
            }
        }
    }

    foreach ($root in @($installedRoot, $requestedInstallRoot, $workRoot)) {
        if ($root -and (Test-Path $root)) {
            Remove-Item $root -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $discoveryPath -Force -ErrorAction SilentlyContinue
}

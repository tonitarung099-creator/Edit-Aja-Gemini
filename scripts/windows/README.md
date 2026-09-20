# Windows build scripts

The Windows workflow is intentionally thin. Each failure domain lives in one
script so fixes can be isolated and reviewed without editing a large YAML file.

| Script | Responsibility |
| --- | --- |
| `reconstruct-source.ps1` | Clone pinned Kdenlive source, apply the patch chain, brand it, verify required P5 features, and archive corresponding source. |
| `bootstrap-craft.ps1` | Download the pinned Craft bootstrap, select MinGW, bootstrap Craft, and apply stable Craft settings. |
| `patch-gettext.ps1` | Apply the MinGW/libxml2 compatibility hotfix to Craft's gettext blueprint. |
| `install-blueprint.ps1` | Copy the prepared Edit Aja Craft blueprint into Craft's KDE blueprint tree. |
| `invoke-craft.ps1` | Run one explicit Craft phase: dependencies, application build, packager install, or package creation. |
| `collect-package.ps1` | Find the produced Windows package and copy runnable artifacts into `artifacts/windows`. |
| `craft-env.ps1` | Shared helper that imports Craft's environment safely. |

Pinned external revisions and patch hashes are stored in
`build/build-manifest.json`. Generated patch inputs are prepared by
`scripts/prepare_build_inputs.py`.

When a build fails, start with the failed GitHub Actions step and edit only the
script responsible for that step. Avoid putting build logic back into
`.github/workflows/build-windows.yml`.


## Packaging image compatibility

`prepare-package-images.ps1 -DependenciesOnly` checks dependency images before
compilation. The full check runs again after compilation, immediately before
Craft packaging, and also requires the application image. Craft's
Windows bootstrap may install toolchain images as `MinSizeRel` while the
application build uses `RelWithDebInfo`. The Craft packager requires an image
directory for every runtime/packaging dependency. Build #51's log confirms
`libs/runtime` installed the MinGW 14.2.0 DLLs in `image-MinSizeRel-14.2.0`,
then packaging looked for `image-RelWithDebInfo-14.2.0`.

The helper permits a temporary directory junction for `libs/runtime` and the
prebuilt MinGW `dev-utils/snoretoast` package, using an exact same-target release
image. SnoreToast must be a `BinaryPackageBase`; a source-built recipe is rejected. Debug images, other versions, missing
application images, and missing images of other dependencies fail explicitly.
It checks all required images before creating any junction. Package exclusions
are initialized in the blueprint constructor so preflight and Craft packaging
use the same dependency set.

Regression tests exercise the dependency traversal and failure paths. The
Windows quality gate also creates a real junction and checks file access,
existing-destination failure, and preservation of the source after removal.
This gate does not replace testing the final installer and application.

## Craft configuration discovery

Build #56 compiled successfully but the external packaging helper searched for
`D:\etc\CraftSettings.ini` instead of the configured installation. The pinned
CraftConfig implementation uses `craftRoot` (the Craft checkout directory) or
the invoked script's location to discover its settings. Neither `CRAFT_ROOT`
nor `KDEROOT` controls that lookup.

The helper validates the installation and sets `craftRoot` before importing
Craft modules. The Windows preflight quality gate now runs the real CLI against
the manifest-pinned Craft checkout, with an isolated configuration and a small
source-only blueprint. It checks external-script invocation, paths with spaces,
a stale locator, and missing settings without downloading the application
dependencies. This tests real Craft initialization, not a mocked configuration.

## Build #60: prebuilt SnoreToast image

Build #60 (`35456970019`) installed SnoreToast 0.7.0 from KDE's prebuilt
MSVC archive during bootstrap. Its post-install log identifies
`image-MinSizeRel-0.7.0`, while packaging requested
`image-RelWithDebInfo-0.7.0`. The pinned Craft configuration fix worked;
preflight stopped because the compatibility exception covered only MinGW's
runtime libraries. No package or application smoke test completed.

The MinGW SnoreToast blueprint copies one upstream binary archive for all
release build types. Reusing that exact-version image preserves its payload;
it does not change or recompile the executable. The guard still rejects Debug,
other versions, unrelated dependencies, and source-built SnoreToast.

The Windows integration test uses the actual pinned Craft dependency resolver,
a BinaryPackageBase fixture, and a real junction. It verifies the fixture
payload is readable, unchanged, and reusable on a second run. It does not claim
to run the actual SnoreToast executable or the final application.

Both the packager installation and dependency-image check now happen before
compiling Edit Aja. The early check skips only the root application image; the
mandatory post-compile check includes it. This catches missing packaging
inputs before spending time on another full application compile.


### Build #61: validate the installer tools themselves

Build #61 (`35483805787`, main `4977b7a`) passed compilation and both image
checks, then created the 129 MiB `.7z`. NSIS failed with `Failed to find 7z`
and `@{7za} is not in variables`. Craft's pinned `_prepare7Z()` reads
`7zip-base.imageDir()/dev-utils/7z/x64/7za.exe`, independently of the working
archive-command shim. Bootstrap had installed 7zip-base 25.01 as MinSizeRel.
The tool is outside the application's runtime/packaging dependency graph.

Both Windows preflight calls now explicitly include the 7zip-base image without
adding developer tools to the shipped application. Only its BinaryPackageBase
recipe may reuse an exact-version release image, and the architecture-specific
payload must exist before any junction is created. Existing incomplete images,
Debug images, wrong versions and source-built tool replacements remain errors.

Preflight then executes NSIS `/VERSION` (minimum 3.03), the archive tool `i`, and
the embedded 7za `i` after calling Craft's actual `_prepare7Z()` copy/signing
routine in a temporary directory. A working PATH shim cannot mask a missing or
broken embedded executable. The normal installer generation remains mandatory.

Regression tests use actual pinned Craft and its 7zip-base recipe, with isolated
image paths and fixture bytes. Windows CI tests the real junction and repeated
runs; executable responses are simulated in these tests. The full Windows build
executes the actual installed tools before compilation. These tests do not prove
NSIS installer generation, app startup, editing, export or release readiness.


## Build #62: first successful Windows package

Build #62 (`35486692474`, main `c1e0ae94...`) completed the full Windows
build and packaging path successfully. Craft produced the NSIS installer
`editaja-HEAD-c3d8a38c04-editaja-windows-gcc-x86_64.exe`, and GitHub uploaded
the `Update-P5-Edit-Aja-Windows-x64` artifact.

Packaging success is not runtime proof. The build workflow therefore runs
`smoke-test-package.ps1` after the Windows artifact has been collected and
uploaded. The smoke test installs the NSIS package silently in CurrentUser mode,
requests an isolated runner directory, then reads Craft/NSIS's registered
`Install_Dir` as the authoritative final install location. It verifies
`bin/kdenlive.exe` and the uninstaller there, runs the packaged executable with
`--version`, launches the GUI process for 15 seconds to reject immediate
startup crashes, then stops the process and uninstalls the test copy.

This proves installer execution, packaged runtime loading, and basic startup on
the Windows runner. It still does not prove project editing, media import,
timeline operations, render/export, optional AI backends, Windows 11 hardware
compatibility, or release readiness; those remain separate verification stages.


### Build #63: smoke test reached installer execution

Build #63 (`35489590662`, main `adb9b27d...`) again passed source
reconstruction, dependencies, Windows compile, packaging, package collection,
and Windows artifact upload. The new runtime smoke step launched the generated
NSIS installer successfully, but then failed before executing the application
because the first smoke implementation assumed the requested `/D=` path was
also the final MultiUser install directory.

The pinned Craft NSIS template writes its final installation directory to
`HKCU\Software\KDE e.V.\Update P5 Edit Aja\Install_Dir` in CurrentUser
mode. The smoke test now reads that installer-owned value after installation
instead of guessing the final path. Build #63 therefore provides no evidence of
an application startup failure; executable probing and GUI startup remained
NOT TESTED in that run.


## Build #64: packaged application startup verified

Build #64 (`35492522303`, main `3641fe737...`) passed the complete Windows
build path and the packaged-app startup smoke. The generated NSIS installer
installed in CurrentUser mode, registered the final install root, exposed the
packaged `bin/kdenlive.exe`, returned `kdenlive 26.11.70` from `--version`,
remained alive for the 15-second GUI startup probe, and uninstalled cleanly.

Startup proof is still not editing proof. The next Windows verification layer
is `functional-smoke-package.ps1`. It installs the same packaged application,
opens a copied Kdenlive test project from the verified corresponding source,
waits for the live localhost agent/REST bridge, validates the native tool
catalog, reads the active project and timeline, performs a native clip split,
adds and reads back a subtitle, and saves a project copy. Each state change is
read back through the running application's native registry before the step can
pass.

Render/export is intentionally kept out of this first functional smoke. It will
be a separate verification boundary so a render failure cannot be confused with
project loading, native timeline editing, subtitle editing, or project saving.


### Native subtitle initialization audit

After Build #64 passed installer/startup smoke and Build #65 began functional
verification, source inspection found that the three agent creation tools
(`kdenlive_add_subtitle`, `kdenlive_import_subtitles`,
`kdenlive_add_subtitle_batch`) read the lazy subtitle model without initializing
it. Projects without subtitle tracks, including the `av.kdenlive` smoke fixture,
can therefore return `Subtitle model is not available` before adding anything.
The native UI calls `showSubtitleTrack()` before adding/importing subtitles.

`patches/subtitle-initialization.patch` uses that same existing initialization
path in the three creation branches. Existing edit, undo, validation, and
read-only operations are preserved. Reconstruction verifies the initializer in
each affected branch. The packaged functional smoke test must still prove that
adding a subtitle to the subtitle-free fixture succeeds; Windows compile and
functional verification of this change remain separate gates.


## Build #65: transient KDE dependency download failure

Build #65 (`35497266457`, main `35a4e886...`) failed before compilation in
`Install dependencies from KDE binary cache`. The first cache-manifest 404 was
not terminal: Craft fell back and continued. The actual terminal failure was a
network connection error while fetching dependencies. The log shows
`wget2 ... failed with exit code 4` / `Failed to connect`, including the
source fallback for `kde/applications/libkexiv2`.

Dependency installation now retries the same Craft command up to three times
with short increasing delays. Craft keeps successfully installed dependencies
between attempts, so a retry resumes from the remaining package set instead of
discarding completed work. Compile, package, and application-runtime commands
are not retried by this rule; deterministic failures in those stages remain
immediate failures.


## Build #66: functional editing reached project save

Build #66 (`35497984665`, main `44013ce1...`) passed source reconstruction,
dependencies, compilation, packaging, artifact upload, packaged install/startup,
REST bridge discovery, native tool catalog checks, project loading, a real
timeline split (2 clips to 4), and native subtitle creation/readback.

The only failing boundary was the next `kdenlive_save_project` call. The
functional-smoke client used the same 30-second HTTP timeout as lightweight
queries and canceled the request exactly when that limit elapsed. That timeout
does not prove the editor save operation failed; the test killed the app during
cleanup immediately afterward.

The smoke client now keeps the 30-second default for normal tools but allows up
to 120 seconds specifically for project save, while logging each native tool
name and elapsed time. The saved copy must still exist, be nontrivial in size,
and leave the active project path unchanged before the save boundary can PASS.
If the native save itself is genuinely stuck, the longer boundary will still
fail and the named timing log will make that failure attributable.


## Build #68: native save-copy blocked by existing-file semantics

Build #68 (`35501973401`, main `6c53685a...`) again passed source
reconstruction, dependencies, compilation, packaging, artifact upload,
installer/startup, REST discovery, project load, a real timeline split
(2 clips to 4), and native subtitle creation/readback. Unlike Builds #66/#67,
the save call had its dedicated 120-second timeout and per-tool timing. The
`kdenlive_save_project` request still did not return within 120 seconds, so
the save boundary is a real native/runtime blocker rather than a 30-second test
artifact.

Source inspection found that the agent tool passed its public `overwrite=true`
permission directly as `ProjectManager::saveFileAs(..., saveOverExistingFile,
...)`. Kdenlive's second parameter is not merely permission; it means the
target is an existing project being overwritten and enables upgraded/modified
project backup notification behavior. The functional smoke saves to a brand-new
copy path, so treating that new path as an existing overwrite can enter the
backup/message-box path. A modal notification has no operator in CI and can
block the REST call indefinitely.

`patches/save-project-agent.patch` now captures whether the target actually
exists before saving. A new path is saved with `saveOverExistingFile=false`;
an existing destination still requires the public `overwrite=true` permission
before the overwrite path is used. Reconstruction and Craft apply the same patch
after the prior native fixes, and source verification requires the corrected
call shape.

# Building Update P5 Edit Aja

The reference Windows build is deliberately gated so an expensive compile does
not become the first debugging tool.

## Source and version contract

The single build manifest is `build/build-manifest.json`. It records:

- the exact Kdenlive commit used as upstream source;
- the exact KDE Craft revision used for Windows builds;
- every compressed P5 patch source and SHA-256;
- the patch application order and strip depth;
- payloads copied into the Craft blueprint.

Do not update a revision or checksum only in a workflow. Update the manifest and
let the quality gates detect mismatches.

## Quality gates before Windows

`.github/workflows/quality-gates.yml` runs on pull requests and `main`.

It verifies:

- repository and Python syntax;
- component tests in parallel by subsystem;
- CLI contracts and examples;
- build manifest/revision consistency;
- compressed patch SHA-256 values;
- workflow YAML;
- PowerShell syntax;
- full source reconstruction on Linux.

The Windows workflow only starts after **P5 Quality Gates** succeeds for a
`main` commit. It checks out the exact tested commit SHA supplied by the
`workflow_run` event.

## Source reconstruction

`scripts/reconstruct_source.py` is the canonical implementation shared by
Linux verification and Windows packaging. It:

1. reconstructs generated patch inputs and verifies their checksums;
2. clones the pinned Kdenlive commit;
3. applies Phase 5, build fixes, Phase 6, Phase 12, Phase 13, Phase 14 and
   Phase 15 in manifest order;
4. copies the Film Context backend;
5. applies Update P5 Edit Aja branding;
6. runs `scripts/verify_p5_source.py`;
7. optionally creates the corresponding-source zip.

`scripts/windows/reconstruct-source.ps1` is intentionally only a thin wrapper
around this shared implementation.

## Windows build chain

After the quality-gated commit is checked out:

1. `scripts/prepare_build_inputs.py` prepares the Craft payload.
2. `scripts/windows/reconstruct-source.ps1` creates and archives the verified
   corresponding source.
3. `scripts/windows/bootstrap-craft.ps1` bootstraps the pinned Craft revision
   with MinGW x64 and `RelWithDebInfo`.
4. `scripts/windows/patch-gettext.ps1` applies the isolated MinGW/libxml2
   compatibility fix.
5. `scripts/windows/install-blueprint.ps1` installs the Edit Aja blueprint.
6. `scripts/windows/invoke-craft.ps1 -Mode install-deps` installs dependencies.
7. `scripts/windows/invoke-craft.ps1 -Mode build` compiles the application.
8. The same script installs the packager and creates the package.
9. `scripts/windows/collect-package.ps1` collects the runnable artifact.
10. GitHub uploads the Windows package and verified corresponding source.

## Debugging boundaries

Use the failed gate/step as the owner of the problem:

- **Static / Repository** -> repository layout, Python/JSON syntax;
- **Component / ...** -> that feature domain only;
- **Contracts / Examples** -> public CLI/example contract;
- **Build / Configuration** -> manifest, checksums, workflow/build helper syntax;
- **Source / Reconstruction** -> upstream source, patch chain, branding/source markers;
- **Bootstrap Craft** -> Craft setup/configuration;
- **gettext** -> MinGW/libxml2 compatibility patch;
- **Install dependencies** -> Craft dependency resolution/cache;
- **Build** -> compiler/CMake/linker;
- **Package** -> packager;
- **Collect package** -> artifact discovery.

Avoid adding temporary repair logic directly to
`.github/workflows/build-windows.yml`. Put fixes in the owning script and add a
regression test when practical.

Update P5 Edit Aja deliberately keeps several Kdenlive internal names and the
`.kdenlive` project extension for compatibility with existing projects,
effects, translations, QML modules, and the Phase 5 MCP/API namespace.

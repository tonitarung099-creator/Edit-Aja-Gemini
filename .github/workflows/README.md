# GitHub Actions

This repository intentionally keeps the workflow surface small.

| Workflow | Responsibility |
| --- | --- |
| `quality-gates.yml` | Runs static checks, parallel component tests, contract/example smoke checks, build configuration validation, and Linux source reconstruction. |
| `build-windows.yml` | Builds and packages the exact `main` commit that successfully completed P5 Quality Gates. |

## Execution order

`P5 Quality Gates` runs first. Independent feature domains run in parallel.
Build configuration is validated separately, then source reconstruction runs
only after build configuration passes.

The Windows workflow is triggered through `workflow_run` and checks out the
exact tested commit SHA. It does not start for a failed quality-gate run or for
a pull-request branch.

## Component failure boundaries

- AI Control
- Media Editorial
- Audio Speech
- Captions
- Visual Segmentation
- Documentary
- Static / Repository
- Contracts / Examples
- Build / Configuration
- Source / Reconstruction

Do not create one workflow per feature. Add feature tests under `tests/` and
place them in the appropriate quality-gate matrix group.

Windows build deduplication is handled by the `concurrency` block in
`build-windows.yml`.

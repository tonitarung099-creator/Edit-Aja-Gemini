# P5 quality gates

P5 Edit Aja uses layered verification so a full Windows build is the final
expensive check, not the first debugging tool.

## Gate order

1. **Static / Repository** — Python syntax, JSON examples, repository layout.
2. **Component tests** — independent feature domains run in parallel.
3. **Contracts / Examples** — CLI contracts and representative example flows.
4. **Build / Configuration** — pinned revisions, checksums, workflow YAML,
   Python build helpers, and PowerShell syntax.
5. **Source / Reconstruction** — reconstruct the pinned Kdenlive source on
   Linux and apply/verify the complete P5 patch chain.
6. **Windows compile** — only a successful `main` quality-gate run can trigger
   the Windows build, which checks out that exact verified commit.
7. **Packaging** — create and collect the Windows artifact.
8. **Release smoke test** — verify the packaged application starts and key
   product flows work.

## Component boundaries

| Gate | Typical ownership |
| --- | --- |
| AI Control | AI Edit, Local Edit, Film Context, capability registry, creator orchestration |
| Media Editorial | media analysis, dialogue, beats, montage, highlights, B-roll |
| Audio Speech | audio analysis, ducking, transcription and cleanup backends |
| Captions | caption generation, animation and speaker handling |
| Visual Segmentation | visual intelligence, SAM adapter and mask effects |
| Documentary | documentary toolkit, graphics and motion templates |
| Build / Configuration | manifest, pinned revisions, workflow syntax, build helpers |
| Source / Reconstruction | upstream source, patch order/application, branding, required source markers |

A green domain should remain untouched while repairing an unrelated red domain
unless failure evidence shows a dependency.

## Debugging rule

When a gate fails:

1. read the actual log;
2. identify the first relevant error;
3. assign the failure to one owner domain;
4. make the smallest root-cause fix;
5. add a regression test when practical;
6. rerun the cheap owning gate before an expensive Windows build.

Do not use repeated full builds as trial-and-error debugging.

## Preserve an active Windows build

Windows build #54 (`35451540981`) was cancelled during compilation at
2026-09-19 15:57:47 UTC. The skipped workflow #55 (`35453425453`) had started
two seconds earlier, after a pull-request quality gate. The old Windows
workflow placed every run in one workflow-level concurrency group with
`cancel-in-progress: true`, including runs whose Windows job would be skipped.
The timing and configuration support concurrency cancellation as the cause;
the job log itself reports only that the operation was canceled.

The scheduling contract is now:

- Only quality-gate completions on `main` trigger the Windows workflow.
- Only a successful gate admits the Windows job to the concurrency group.
- The active Windows job finishes even when a newer verified commit arrives.
- GitHub's default single pending slot keeps the newest waiting job; intermediate
  pending jobs may be replaced. This does not guarantee every commit is built.
- Checkout uses the gate's exact `head_sha`, so an older build completing after
  a new commit must not be reported as verification of the newer source.

These are configuration guarantees, not protection against manual cancellation,
runner failure, or timeout. See
[GitHub's concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

`tests/test_build_workflow.py` protects this policy with parsed-YAML checks.
Run it with `python -m unittest tests.test_build_workflow -v` after installing
the same `PyYAML==6.0.3` used by the configuration quality gate. Local tests
verify the configuration; actual queue behavior still requires GitHub execution.

When first integrating this change, wait until the existing Windows run has
finished before opening the PR: the old default-branch workflow is still used
for `workflow_run` events and can cancel an active build when PR checks finish.
Then open the PR, require its quality gates to pass, merge, and verify scheduling
on the resulting main commit. Do not bypass checks to install the new policy.

## Packaged-application failure evidence

The Windows build uploads `Update-P5-Edit-Aja-Smoke-Diagnostics` even when a
smoke test fails, provided packaging succeeded. The `startup` and `functional`
folders contain application stdout/stderr and a `result.json` recording the
last attempted stage, PASS/FAIL, workflow run, and checked-out source commit.
Missing folders mean that test did not reach diagnostic collection.

Bridge discovery credentials are never uploaded. Known discovery tokens and
Bearer credentials are redacted from logs; malformed discovery data suppresses
raw-log export while retaining the stage report. Diagnostics are retained for
14 days. Process checks stop startup/bridge/project-load polling when the
application has exited; cleanup warnings do not replace the original failure.

`tests/test_smoke_support.ps1` exercises process exit detection and diagnostic
export on the Windows quality gate before the full build. A smoke PASS covers
only that script's assertions: startup, or project load/split/subtitle/save-copy.
It does not prove video export, saved-project reopening, or successful uninstall.

Build #70 (`35510901540`, source `17a3693e7bf7b25ae2a2f6f21c027229da3737aa`)
passed the functional assertions, including save-copy in 0.1 seconds, but its
functional diagnostic export warned about a null-valued method call. The cheap
Windows regression in PR #33 reproduced that warning with a zero-byte stdout
file and a discovery token. Diagnostic collection now uses `ReadAllText` to
obtain an actual empty string before redaction. The regression checks that
empty stdout does not prevent stderr redaction or the PASS/FAIL stage report.

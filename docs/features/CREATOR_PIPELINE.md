# Creator Pipeline

Creator Pipeline connects Update P5's separate intelligence engines without turning them into one monolithic AI agent.

A pipeline JSON can:

- run repo-local tools in a defined order,
- pass named artifacts from one stage to another,
- mark expensive/optional stages as optional,
- capture stdout/stderr and return codes,
- collect every Phase 6 `*.edit.json` plan,
- compose those plans into one final deterministic AI Edit JSON.

## Tokens

Use double-brace tokens:

```text
{{root}}
{{workdir}}
{{MY_VARIABLE}}
{{stage-id.output-name}}
```

## Example

```text
python tools/creator_pipeline/creator_pipeline.py \
  examples/creator/documentary-pipeline.json \
  --workdir ./creator-output \
  --report ./creator-output/pipeline-report.json
```

The example chains phrase captions, transcript B-roll planning/placeholders and optional beat cuts, then creates:

```text
creator-output/final.edit.json
```

Preview the resolved commands without running them:

```text
python tools/creator_pipeline/creator_pipeline.py pipeline.json --dry-run
```

This becomes the backend for a future one-click Creator Workspace: individual engines remain independent and replaceable, while the pipeline defines how they are combined for a particular editing workflow.

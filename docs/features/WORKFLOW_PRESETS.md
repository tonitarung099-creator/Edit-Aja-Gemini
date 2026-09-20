# Creator Workflow Presets

Workflow Presets generate ready-to-run **Creator Pipeline** configs for common editing jobs.

Available presets:

- `documentary`
- `talking-head`
- `podcast`
- `shorts`

## Documentary

Includes phrase captions, transcript-driven B-roll planning/placeholders, bad-take review and optional beat cuts.

```text
python tools/workflow_presets/workflow_presets.py documentary \
  --transcript transcript.json \
  --rhythm rhythm.json \
  --output pipeline.json
```

## Talking head

Includes readable captions, dialogue review, bad-take review and social-highlight candidates.

## Podcast

Includes speaker-aware captions, bad-take review and longer highlight candidates.

## Shorts

Includes animated word captions, highlight candidates and optional vertical Smart Reframe when a subject track is available.

```text
python tools/workflow_presets/workflow_presets.py shorts \
  --transcript transcript.json \
  --subject-track person-track.json \
  --output shorts-pipeline.json
```

The generated JSON is then executed by `tools/creator_pipeline/creator_pipeline.py`. Presets are only workflow definitions; the individual engines remain independent and replaceable.

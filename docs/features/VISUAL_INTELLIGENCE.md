# Visual Intelligence

Visual Intelligence adds an editable **smart reframe** pipeline without replacing the existing AI Agent.

## Subject-track format

A subject track uses normalized coordinates where `x=0..1` and `y=0..1`:

```json
{
  "format": "update-p5-subject-track",
  "version": 1,
  "samples": [
    {"time_seconds": 0.0, "x": 0.42, "y": 0.40, "confidence": 0.9},
    {"time_seconds": 1.2, "x": 0.58, "y": 0.42, "confidence": 0.9}
  ]
}
```

This decouples **tracking** from **editing**. A face detector, object tracker, SAM-style model, or external AI can all produce the same normalized track.

## Smart reframe

```text
python tools/visual_intelligence/visual_intelligence.py reframe subject-track.json \
  --preset vertical \
  --output vertical-reframe.json
```

Presets:

- `vertical` — 1080×1920, stronger zoom,
- `square` — 1080×1080,
- `portrait` — 1080×1350,
- `landscape` — 1920×1080.

The generated Phase 6 plan cuts only when framing decisions change meaningfully, then applies Kdenlive's native Transform effect to each segment. The timeline remains editable.

## Optional OpenCV face backend

If OpenCV is installed separately:

```text
python tools/visual_intelligence/visual_intelligence.py face-track input.mp4 \
  --output face-track.json
```

Then:

```text
python tools/visual_intelligence/visual_intelligence.py reframe face-track.json \
  --preset vertical \
  --output vertical-edit.json
```

OpenCV is intentionally optional and is not forced into the base editor package. Later object-tracking or SAM-style backends can emit the same subject-track format.

# Auto Ducking

Auto Ducking creates **native timeline edits** that lower a music clip under spoken dialogue.

It reads timestamped speech segments, adds configurable lead/tail padding, merges nearby ranges, cuts the selected music clip at those boundaries, then applies a lower native clip volume only to the speech sections.

## Usage

```text
python tools/auto_ducking/auto_ducking.py transcript.json \
  --music-track-index 0 \
  --duck-gain-db -14 \
  --output music-ducking.edit.json
```

Defaults:

- lead: 0.18 s
- tail: 0.25 s
- nearby speech merge gap: 0.15 s
- duck amount: -14 dB

The generated Phase 6 JSON remains editable because the music track is split into ordinary clips and the volume change uses `kdenlive_set_clip_volume`. No destructive audio rendering is required.

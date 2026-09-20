# Smart Montage Builder

Smart Montage Builder combines **Rhythm Intelligence** with a list of B-roll/image/video assets and creates a native beat-synced montage track.

## Workflow

```text
music/video
   ↓
Rhythm Intelligence
   ↓
rhythm.json + beat timestamps

B-roll / AI images / archive footage
   ↓
smart-montage.json
   ↓
Smart Montage Builder
   ↓
Phase 6 AI Edit JSON
   ↓
native clips on a montage track
```

## Example

```text
python tools/smart_montage/smart_montage.py rhythm.json \
  examples/documentary/smart-montage.json \
  --start 10 \
  --end 30 \
  --every 2 \
  --output montage.edit.json
```

The builder:

- creates a dedicated video track,
- imports each asset,
- places it at the selected beat boundary,
- resizes it to the interval before the next selected beat,
- optionally applies native Transform scale/position,
- can cycle assets if the montage has more intervals than source files.

This is especially useful for AI-generated documentary images: GPT can decide the visual sequence, image generation can create the files, and Update P5 can assemble the results to music without flattening the timeline.

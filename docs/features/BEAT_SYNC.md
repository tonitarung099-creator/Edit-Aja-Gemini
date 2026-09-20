# Beat Sync Editing

Beat Sync Editing converts beat timestamps from **Rhythm Intelligence** into native timeline cut points.

## Example

First analyze the media/music:

```text
python tools/rhythm_intelligence/rhythm_intelligence.py music-video.mp4 \
  --output rhythm.json
```

Then create cuts:

```text
python tools/beat_sync/beat_sync.py rhythm.json \
  --every 2 \
  --video-track-index 0 \
  --output beat-cuts.edit.json
```

Controls include:

- `--every 1` — every detected beat,
- `--every 2` / `--every 4` — slower montage rhythm,
- `--offset` — shift which beat in the pattern is used,
- `--min-strength` — ignore weak beat candidates,
- `--start / --end` — limit the montage section.

The result uses native `kdenlive_cut_clip` operations and remains fully editable.

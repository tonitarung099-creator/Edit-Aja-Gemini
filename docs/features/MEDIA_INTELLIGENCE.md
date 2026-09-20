# Phase 7 — Media Intelligence

Phase 7 adds useful analysis features **before** adding more UI. It uses FFmpeg/FFprobe, which already fit naturally with the Kdenlive/MLT toolchain, and does not require extra Python packages.

## Implemented

- media metadata normalization with FFprobe,
- silence/pause detection,
- scene/shot cut detection using FFmpeg scene scores,
- black-frame range detection,
- EBU loudness analysis through `loudnorm`,
- pacing summary from scene durations,
- smart silence-cut range generation,
- direct export of smart cuts as Phase 6 `update-p5-ai-edit` JSON.

## Analyze a video

```text
python tools/media_intelligence/media_intelligence.py analyze video.mp4 --output analysis.json
```

The report includes duration, codecs, resolution/FPS, audio format, silence ranges, scene cut times, pacing statistics, black ranges and loudness measurements.

Useful tuning options:

```text
--noise-db -35
--silence-duration 0.5
--scene-threshold 0.35
--black-duration 0.5
--black-threshold 0.98
```

## Generate a smart jump-cut plan

```text
python tools/media_intelligence/media_intelligence.py smart-cut video.mp4 --output smart-cut.json
```

The generated file can be opened by Update P5's Phase 6 AI Edit importer or applied with the Phase 6 runner.

The cutter keeps a small amount of audio at both sides of every pause by default to avoid robotic cuts:

```text
--edge-keep 0.12
```

Other controls:

```text
--min-remove 0.35
--keep-start 1.0
--keep-end 1.0
--merge-gap 0.04
--video-track-index 0
--audio-track-index 0
--video-only
```

## Design

Phase 7 deliberately produces analysis data and edit decisions separately:

```text
MP4
 ↓
FFmpeg / FFprobe analysis
 ↓
media-analysis.json
 ↓
smart edit decision
 ↓
update-p5-ai-edit JSON
 ↓
Phase 6
 ↓
native editable timeline
```

This keeps automatic analysis replaceable later. A future PySceneDetect, whisper.cpp, DeepFilterNet, or other backend can feed the same native editing layer without rewriting timeline logic.

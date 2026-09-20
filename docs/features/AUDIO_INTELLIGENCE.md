# Audio Intelligence

Audio Intelligence measures source audio with FFmpeg `loudnorm` and converts the measurement into an editable native timeline operation.

Current features:

- integrated LUFS measurement,
- true-peak measurement,
- bounded gain recommendation,
- true-peak safety limiting,
- configurable target loudness,
- native `kdenlive_set_clip_volume` plan generation,
- optional native fade-in/fade-out generation.

## Analyze loudness

```text
python tools/audio_intelligence/audio_intelligence.py voice.mp4
```

Default target is `-16 LUFS`, a common spoken-content target. Change it explicitly when the delivery platform or production requires another target.

## Generate an editable normalization plan

```text
python tools/audio_intelligence/audio_intelligence.py voice.mp4 \
  --plan \
  --target-lufs -16 \
  --fade-in 0.15 \
  --fade-out 0.25 \
  --output audio-normalize.json
```

The generated JSON uses the Phase 6 live `$clip_at` selector to find the audio clip on the selected audio track, then applies Kdenlive's native Volume and Fade tools. It does not destructively rewrite the media file.

Safety limits default to:

- maximum boost: +8 dB,
- maximum cut: -12 dB,
- true peak ceiling: -1.5 dB.

These limits are configurable.

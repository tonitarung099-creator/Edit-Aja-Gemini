# Rhythm Intelligence

Rhythm Intelligence adds two lightweight analyses without extra Python packages:

- **visual motion/activity detection** from low-resolution grayscale frame differences,
- **audio beat detection** from short-time RMS energy novelty.

FFmpeg supplies decoded frames/audio; the analysis itself uses only Python's standard library.

## Usage

```text
python tools/rhythm_intelligence/rhythm_intelligence.py video.mp4 \
  --output rhythm.json
```

Useful controls:

```text
--motion-fps 4
--motion-threshold 0.055
--beat-sensitivity 1.6
--beat-min-interval 0.22
```

The report contains:

- motion score samples,
- merged activity ranges,
- detected beat timestamps,
- an estimated BPM when enough beat intervals exist.

This data is intentionally separate from editing decisions. ChatGPT, the built-in agent, or later deterministic tools can use beat timestamps for music-synced cuts and activity ranges for B-roll selection without changing the underlying detector.

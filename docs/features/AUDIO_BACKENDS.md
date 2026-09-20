# Optional DeepFilterNet Backend

Update P5 can use the external **DeepFilterNet** `deep-filter` executable for local speech/noise enhancement.

The base editor does not bundle DeepFilterNet or model weights. This keeps the normal installation lighter and makes the enhancement backend optional.

## Workflow

```text
source video/audio
      ↓
FFmpeg → 48 kHz WAV
      ↓
deep-filter
      ↓
cleaned WAV
      ↓
optional Phase 6 plan
      ↓
new native audio track + mute original clip
```

## Usage

```text
python tools/audio_backends/deepfilternet.py interview.mp4 \
  --output-audio interview-clean.wav \
  --plan-output interview-clean.edit.json
```

Optional controls include a custom model tarball, postfilter, delay compensation, original audio track index and keeping the original audio audible.

The generated plan does not destructively replace the source file. It imports the enhanced WAV on a new audio track and, by default, applies `-100 dB` to the original timeline audio clip. Undo/checkpoint behavior remains available through Phase 6.

# Optional whisper.cpp Backend

Update P5 can use the external `whisper-cli` binary from **whisper.cpp** as an optional fully-local transcription backend.

The adapter deliberately does **not** bundle whisper.cpp or model weights. This keeps the base editor smaller and lets users choose CPU/GPU builds and model sizes independently.

The adapter follows whisper.cpp's current CLI JSON output contract:

- `whisper-cli`
- `--output-json-full`
- segment `offsets.from/to`
- optional token-level timestamps.

## Usage

```text
python tools/speech_backends/whispercpp.py video.mp4 \
  --model /path/to/ggml-base.bin \
  --output transcript.json
```

The media is converted to 16 kHz mono PCM WAV with FFmpeg before inference.

To produce native subtitle editing JSON directly:

```text
python tools/speech_backends/whispercpp.py video.mp4 \
  --model /path/to/ggml-base.bin \
  --format ai-edit \
  --output subtitles.edit.json
```

For creator-style phrase or word-by-word captions, generate `transcript.json` first and pass it through `tools/caption_intelligence/caption_intelligence.py`.

## Dependency policy

whisper.cpp is an optional external backend. Update P5 does not silently download models or execute remote services. Model selection, storage and acceleration remain under the user's control.

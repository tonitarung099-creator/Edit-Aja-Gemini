# Animated Captions

Animated Captions turns word-level timestamps into editable native **title clips** with simple motion presets.

Presets:

- `clean` — static word,
- `pop` — scale in, overshoot, settle,
- `punch` — strong initial emphasis,
- `bounce` — multi-step bounce.

## Example

```text
python tools/animated_captions/animated_captions.py transcript.json \
  --preset pop \
  --font-size 78 \
  --output animated-captions.edit.json
```

The tool expects the `words` array produced by the whisper.cpp adapter. Each word becomes one or more short title segments on a dedicated video track, and each segment receives a native Transform scale.

This approach deliberately favors **editable deterministic timeline clips** over a flattened caption render. It also avoids relying on unstable effect-keyframe parameter layouts. For very long transcripts, use `--max-words` during testing because animated word captions can create many timeline items.

# Capability Registry / Doctor

Update P5 contains optional engines with very different dependency profiles. The Capability Registry lets the project inspect the current laptop and report which features are immediately ready.

## Run

```text
python tools/capability_registry/capability_registry.py
```

JSON output for a future UI/agent:

```text
python tools/capability_registry/capability_registry.py --json
```

Filter:

```text
python tools/capability_registry/capability_registry.py --category visual-backend
python tools/capability_registry/capability_registry.py --id sam2
```

The registry checks:

- local tool scripts,
- required executables such as FFmpeg, FFprobe, whisper-cli and deep-filter,
- optional Python modules such as OpenCV and SAM 2/PyTorch.

Optional backends are reported separately from required core features. This gives a future Update P5 settings screen or AI Agent a single source of truth for feature availability instead of hard-coding dependency checks in many places.

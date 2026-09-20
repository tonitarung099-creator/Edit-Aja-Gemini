# Mask Effects

Mask Effects consumes the portable `update-p5-mask-track` format produced by SAM 2 or any future segmentation backend.

Implemented effects:

- **foreground** — transparent subject/cutout video,
- **background_blur** — subject stays sharp, background is blurred,
- **object_blur** — only the selected object is blurred,
- **replace_background** — selected foreground composited over another background image/video.

## Example

```text
python tools/mask_effects/mask_effects.py video.mp4 mask-track.json person \
  --mode background_blur \
  --output portrait-blur.mp4 \
  --plan-output portrait-blur.edit.json
```

Background replacement:

```text
python tools/mask_effects/mask_effects.py video.mp4 mask-track.json person \
  --mode replace_background \
  --background studio.jpg \
  --output replaced.mp4
```

The mask effect renderer is intentionally separate from SAM 2. Any backend that writes the same mask-track contract can use these effects. The optional Phase 6 plan imports the rendered asset onto a native video track, leaving the original source untouched.

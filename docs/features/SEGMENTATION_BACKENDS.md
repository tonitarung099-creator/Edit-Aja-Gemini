# Optional SAM 2 Segmentation Backend

Update P5 can use **SAM 2 / SAM 2.1** as an optional object/video segmentation backend.

SAM 2 is **not bundled** with the normal editor. The adapter imports it only when this tool is run. This avoids forcing PyTorch, CUDA, large checkpoints, or model downloads on every Update P5 installation.

Current pipeline:

```text
video + point/box prompt
        ↓
SAM 2 video predictor
        ↓
mask PNG for every tracked frame
        ↓
update-p5-mask-track.json
        ├─→ normalized subject-track → Smart Reframe
        └─→ transparent foreground MOV → native timeline import
```

## Prompt format

```json
{
  "objects": [
    {
      "id": "person",
      "frame_idx": 0,
      "points": [[960, 540]],
      "labels": [1]
    }
  ]
}
```

Box prompts are also supported:

```json
{"id":"car","frame_idx":0,"box":[420,300,1200,900]}
```

## Local checkpoint mode

Install SAM 2 separately, then provide its config and checkpoint:

```text
python tools/segmentation_backends/sam2_video.py video.mp4 prompt.json \
  --config sam2/configs/sam2.1/sam2.1_hiera_s.yaml \
  --checkpoint sam2.1_hiera_small.pt \
  --output-dir masks \
  --mask-track mask-track.json
```

## Hugging Face mode

```text
--model-id facebook/sam2-hiera-small
```

This mode may download model files, so it is explicit rather than automatic.

## Smart Reframe bridge

```text
--subject-object-id person --subject-track person-track.json
```

The generated subject track is directly compatible with `tools/visual_intelligence/visual_intelligence.py`.

## Background removal / transparent foreground

```text
--cutout-object-id person \
--cutout subject.mov \
--cutout-plan subject.edit.json
```

The adapter uses the tracked grayscale mask sequence as alpha and creates a transparent QTRLE MOV with FFmpeg. The Phase 6 plan imports that asset on a new native video track.

SAM 2 upstream code/checkpoints are currently Apache-2.0 licensed; distribution builds should still audit the exact model/checkpoint and dependency set being shipped.

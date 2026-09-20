#!/usr/bin/env python3
"""Optional SAM 2 video segmentation backend for Update P5 Edit Aja.

SAM 2 is not bundled. This adapter imports it lazily, accepts point/box prompts,
tracks objects through a video, writes one grayscale PNG mask per frame, emits a
portable mask-track JSON, derives a normalized subject track for smart reframe,
and can optionally build a transparent foreground video with FFmpeg.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class Sam2Error(RuntimeError):
    pass


def _exe(name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise Sam2Error(f"{name} was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise Sam2Error(f"Could not execute {args[0]}: {exc}") from exc


def probe_fps(video: Path, ffprobe: str) -> float:
    proc = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=avg_frame_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ]
    )
    if proc.returncode != 0:
        raise Sam2Error(proc.stderr.strip() or "ffprobe failed")
    value = proc.stdout.strip()
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            den_f = float(den)
            fps = float(num) / den_f if den_f else 0.0
        except ValueError as exc:
            raise Sam2Error(f"Invalid FPS from ffprobe: {value!r}") from exc
    else:
        try:
            fps = float(value)
        except ValueError as exc:
            raise Sam2Error(f"Invalid FPS from ffprobe: {value!r}") from exc
    if fps <= 0:
        raise Sam2Error(f"Invalid FPS: {fps}")
    return fps


def load_prompts(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Sam2Error(f"Invalid prompt JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("objects", data.get("prompts"))
    if not isinstance(data, list) or not data:
        raise Sam2Error("Prompt JSON must contain a non-empty objects/prompts array")
    out = []
    ids: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise Sam2Error(f"Prompt #{index + 1} must be an object")
        obj_id = str(item.get("id", index + 1))
        if obj_id in ids:
            raise Sam2Error(f"Duplicate object id: {obj_id}")
        ids.add(obj_id)
        try:
            frame_idx = int(item.get("frame_idx", 0))
        except (TypeError, ValueError) as exc:
            raise Sam2Error(f"Invalid frame_idx for object {obj_id}") from exc
        points = item.get("points")
        labels = item.get("labels")
        box = item.get("box")
        if points is None and box is None:
            raise Sam2Error(f"Object {obj_id} requires points or box")
        if points is not None:
            if not isinstance(points, list) or not points:
                raise Sam2Error(f"Object {obj_id}: points must be a non-empty array")
            normalized_points = []
            for p in points:
                if not isinstance(p, list) or len(p) != 2:
                    raise Sam2Error(f"Object {obj_id}: each point must be [x,y]")
                normalized_points.append([float(p[0]), float(p[1])])
            points = normalized_points
            if labels is None:
                labels = [1] * len(points)
            if not isinstance(labels, list) or len(labels) != len(points):
                raise Sam2Error(f"Object {obj_id}: labels must match points length")
            labels = [int(x) for x in labels]
        if box is not None:
            if not isinstance(box, list) or len(box) != 4:
                raise Sam2Error(f"Object {obj_id}: box must be [x0,y0,x1,y1]")
            box = [float(x) for x in box]
        out.append(
            {
                "id": obj_id,
                "frame_idx": frame_idx,
                "points": points,
                "labels": labels,
                "box": box,
            }
        )
    return out


def mask_geometry(mask: Any) -> dict[str, Any] | None:
    """Return bbox/centroid using a torch boolean mask without importing torch here."""
    coords = mask.nonzero(as_tuple=False)
    if coords.numel() == 0:
        return None
    ys = coords[:, -2]
    xs = coords[:, -1]
    min_x = int(xs.min().item())
    max_x = int(xs.max().item())
    min_y = int(ys.min().item())
    max_y = int(ys.max().item())
    cx = float(xs.float().mean().item())
    cy = float(ys.float().mean().item())
    height = int(mask.shape[-2])
    width = int(mask.shape[-1])
    area = int(coords.shape[0])
    return {
        "bbox": [min_x, min_y, max_x + 1, max_y + 1],
        "centroid": [cx, cy],
        "centroid_normalized": [cx / max(1, width - 1), cy / max(1, height - 1)],
        "area_pixels": area,
        "area_ratio": area / max(1, width * height),
        "width": width,
        "height": height,
    }


def _safe_object_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return cleaned or "object"


def _load_predictor(args: argparse.Namespace) -> Any:
    try:
        if args.model_id:
            from sam2.sam2_video_predictor import SAM2VideoPredictor  # type: ignore
            return SAM2VideoPredictor.from_pretrained(args.model_id, vos_optimized=args.vos_optimized)
        from sam2.build_sam import build_sam2_video_predictor  # type: ignore
    except ImportError as exc:
        raise Sam2Error(
            "SAM 2 is optional and is not installed. Install facebookresearch/sam2 "
            "in a separate Python environment, or skip this backend."
        ) from exc
    if not args.config or not args.checkpoint:
        raise Sam2Error("Use --model-id, or provide both --config and --checkpoint")
    if not args.checkpoint.exists():
        raise Sam2Error(f"Checkpoint not found: {args.checkpoint}")
    return build_sam2_video_predictor(
        args.config,
        str(args.checkpoint),
        vos_optimized=args.vos_optimized,
    )


def run_tracking(
    video: Path,
    prompts: list[dict[str, Any]],
    output_dir: Path,
    *,
    predictor: Any,
    fps: float,
    threshold: float = 0.0,
    offload_video_to_cpu: bool = False,
    offload_state_to_cpu: bool = False,
) -> dict[str, Any]:
    try:
        import torch  # type: ignore
        from torchvision.io import write_png  # type: ignore
    except ImportError as exc:
        raise Sam2Error("SAM 2 backend requires torch and torchvision") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    state = predictor.init_state(
        str(video),
        offload_video_to_cpu=offload_video_to_cpu,
        offload_state_to_cpu=offload_state_to_cpu,
    )
    for prompt in prompts:
        kwargs: dict[str, Any] = {
            "inference_state": state,
            "frame_idx": prompt["frame_idx"],
            "obj_id": prompt["id"],
        }
        if prompt.get("points") is not None:
            kwargs["points"] = prompt["points"]
            kwargs["labels"] = prompt["labels"]
        if prompt.get("box") is not None:
            kwargs["box"] = prompt["box"]
        predictor.add_new_points_or_box(**kwargs)

    objects: dict[str, dict[str, Any]] = {
        str(p["id"]): {"id": str(p["id"]), "frames": []} for p in prompts
    }
    for frame_idx, obj_ids, masks in predictor.propagate_in_video(state):
        for obj_pos, obj_id in enumerate(obj_ids):
            obj_key = str(obj_id)
            logits = masks[obj_pos]
            while logits.dim() > 2:
                logits = logits[0]
            mask = logits > threshold
            geom = mask_geometry(mask)
            safe = _safe_object_id(obj_key)
            path = output_dir / f"object-{safe}-{int(frame_idx):06d}.png"
            image = mask.to(dtype=torch.uint8).mul(255).cpu().unsqueeze(0)
            write_png(image, str(path), compression_level=6)
            entry: dict[str, Any] = {
                "frame_idx": int(frame_idx),
                "time_seconds": int(frame_idx) / fps,
                "mask_path": str(path.resolve()),
            }
            if geom is not None:
                entry.update(geom)
            objects.setdefault(obj_key, {"id": obj_key, "frames": []})["frames"].append(entry)

    return {
        "format": "update-p5-mask-track",
        "version": 1,
        "engine": "sam2",
        "source_video": str(video.resolve()),
        "fps": fps,
        "objects": list(objects.values()),
    }


def subject_track(mask_track: dict[str, Any], object_id: str) -> dict[str, Any]:
    objects = mask_track.get("objects", [])
    obj = next((x for x in objects if str(x.get("id")) == str(object_id)), None)
    if not isinstance(obj, dict):
        raise Sam2Error(f"Object id not found in mask track: {object_id}")
    samples = []
    for frame in obj.get("frames", []):
        if not isinstance(frame, dict):
            continue
        centroid = frame.get("centroid_normalized")
        if not isinstance(centroid, list) or len(centroid) != 2:
            continue
        samples.append(
            {
                "time_seconds": float(frame["time_seconds"]),
                "x": float(centroid[0]),
                "y": float(centroid[1]),
                "confidence": min(1.0, max(0.05, float(frame.get("area_ratio", 0.05)) * 5.0)),
            }
        )
    if not samples:
        raise Sam2Error(f"Object {object_id} has no usable centroid samples")
    return {
        "format": "update-p5-subject-track",
        "version": 1,
        "engine": "sam2",
        "object_id": str(object_id),
        "samples": samples,
    }


def build_cutout(
    video: Path,
    masks_dir: Path,
    object_id: str,
    output: Path,
    *,
    fps: float,
    ffmpeg: str,
) -> None:
    safe = _safe_object_id(str(object_id))
    pattern = masks_dir / f"object-{safe}-%06d.png"
    if not (masks_dir / f"object-{safe}-000000.png").exists():
        raise Sam2Error(
            "Transparent cutout currently requires a mask starting at frame 0 "
            f"for object {object_id}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-framerate",
            f"{fps:.8f}",
            "-start_number",
            "0",
            "-i",
            str(pattern),
            "-filter_complex",
            "[0:v][1:v]alphamerge,format=rgba",
            "-an",
            "-c:v",
            "qtrle",
            "-shortest",
            str(output),
        ]
    )
    if proc.returncode != 0:
        raise Sam2Error(proc.stderr.strip() or "FFmpeg transparent cutout generation failed")


def cutout_plan(cutout: Path, *, at: float = 0.0, track_name: str = "AI Subject Cutout") -> dict[str, Any]:
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "SAM 2 foreground cutout",
            "generated_by": "Update P5 SAM 2 backend",
            "asset": str(cutout.resolve()),
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-sam2-cutout"},
        "steps": [
            {
                "id": "sam2-track",
                "tool": "kdenlive_add_track",
                "arguments": {"audio": False, "name": track_name},
            },
            {
                "id": "sam2-import",
                "tool": "kdenlive_import_media",
                "arguments": {"path": str(cutout.resolve())},
            },
            {
                "id": "sam2-insert",
                "tool": "kdenlive_insert_bin_clip",
                "arguments": {
                    "bin_id": {"$ref": "sam2-import.result.bin_id"},
                    "track_id": {"$ref": "sam2-track.result.track_id"},
                    "position_seconds": at,
                    "use_targets": False,
                },
            },
            {"id": "save-after-sam2", "tool": "kdenlive_save_project", "arguments": {}},
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Optional SAM 2 video segmentation backend")
    p.add_argument("video", type=Path)
    p.add_argument("prompts", type=Path, help="JSON point/box prompts")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--mask-track", type=Path, required=True)
    p.add_argument("--subject-object-id")
    p.add_argument("--subject-track", type=Path)
    p.add_argument("--cutout-object-id")
    p.add_argument("--cutout", type=Path)
    p.add_argument("--cutout-plan", type=Path)
    p.add_argument("--at", type=float, default=0.0)
    p.add_argument("--model-id", help="Hugging Face SAM 2 model id; may download model files")
    p.add_argument("--config", help="Local SAM 2 config path/name")
    p.add_argument("--checkpoint", type=Path)
    p.add_argument("--vos-optimized", action="store_true")
    p.add_argument("--threshold", type=float, default=0.0)
    p.add_argument("--offload-video-to-cpu", action="store_true")
    p.add_argument("--offload-state-to-cpu", action="store_true")
    p.add_argument("--ffmpeg")
    p.add_argument("--ffprobe")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.video.exists():
            raise Sam2Error(f"Video not found: {args.video}")
        prompts = load_prompts(args.prompts)
        ffprobe = _exe("ffprobe", args.ffprobe)
        fps = probe_fps(args.video, ffprobe)
        predictor = _load_predictor(args)
        track = run_tracking(
            args.video,
            prompts,
            args.output_dir,
            predictor=predictor,
            fps=fps,
            threshold=args.threshold,
            offload_video_to_cpu=args.offload_video_to_cpu,
            offload_state_to_cpu=args.offload_state_to_cpu,
        )
        args.mask_track.parent.mkdir(parents=True, exist_ok=True)
        args.mask_track.write_text(json.dumps(track, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote mask track: {args.mask_track}")

        if args.subject_object_id:
            if args.subject_track is None:
                raise Sam2Error("--subject-object-id requires --subject-track")
            subject = subject_track(track, args.subject_object_id)
            args.subject_track.parent.mkdir(parents=True, exist_ok=True)
            args.subject_track.write_text(json.dumps(subject, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Wrote subject track: {args.subject_track}")

        if args.cutout_object_id:
            if args.cutout is None:
                raise Sam2Error("--cutout-object-id requires --cutout")
            ffmpeg = _exe("ffmpeg", args.ffmpeg)
            build_cutout(
                args.video,
                args.output_dir,
                args.cutout_object_id,
                args.cutout,
                fps=fps,
                ffmpeg=ffmpeg,
            )
            print(f"Wrote transparent foreground: {args.cutout}")
            if args.cutout_plan:
                plan = cutout_plan(args.cutout, at=args.at)
                args.cutout_plan.parent.mkdir(parents=True, exist_ok=True)
                args.cutout_plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                print(f"Wrote cutout edit plan: {args.cutout_plan}")
        return 0
    except (Sam2Error, OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

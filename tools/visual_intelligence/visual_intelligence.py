#!/usr/bin/env python3
"""Visual intelligence for Update P5 Edit Aja.

Creates deterministic smart-reframe plans from a normalized subject track.
An optional OpenCV backend can produce a simple face track. The generated plan
uses native Phase 6 timeline cuts + Transform operations, so the result stays
editable.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


class VisualError(RuntimeError):
    pass


PRESETS: dict[str, tuple[int, int, float]] = {
    "vertical": (1080, 1920, 180.0),
    "square": (1080, 1080, 135.0),
    "portrait": (1080, 1350, 150.0),
    "landscape": (1920, 1080, 115.0),
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def load_track(path: Path) -> list[dict[str, float]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualError(f"Invalid subject-track JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("samples", data.get("track", data.get("points")))
    if not isinstance(data, list):
        raise VisualError("Subject track must be an array or contain samples/track/points")
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            t = float(item.get("time_seconds", item.get("time", item.get("t"))))
            x = float(item.get("x"))
            y = float(item.get("y"))
        except (TypeError, ValueError):
            continue
        if t < 0:
            continue
        result.append(
            {
                "time_seconds": t,
                "x": _clamp(x, 0.0, 1.0),
                "y": _clamp(y, 0.0, 1.0),
                "confidence": _clamp(float(item.get("confidence", 1.0)), 0.0, 1.0),
            }
        )
    result.sort(key=lambda p: p["time_seconds"])
    if not result:
        raise VisualError("Subject track contains no valid points")
    return result


def smooth_track(samples: list[dict[str, float]], alpha: float = 0.35) -> list[dict[str, float]]:
    if not 0 < alpha <= 1:
        raise VisualError("smoothing alpha must be > 0 and <= 1")
    out: list[dict[str, float]] = []
    sx = sy = None
    for item in samples:
        sx = item["x"] if sx is None else alpha * item["x"] + (1 - alpha) * sx
        sy = item["y"] if sy is None else alpha * item["y"] + (1 - alpha) * sy
        out.append({**item, "x": sx, "y": sy})
    return out


def simplify_track(
    samples: list[dict[str, float]],
    *,
    min_interval: float = 0.8,
    movement_threshold: float = 0.08,
    confidence_threshold: float = 0.25,
) -> list[dict[str, float]]:
    filtered = [p for p in samples if p.get("confidence", 1.0) >= confidence_threshold]
    if not filtered:
        raise VisualError("No subject samples pass the confidence threshold")
    kept = [filtered[0]]
    for item in filtered[1:]:
        prev = kept[-1]
        dt = item["time_seconds"] - prev["time_seconds"]
        movement = math.hypot(item["x"] - prev["x"], item["y"] - prev["y"])
        if dt >= min_interval or movement >= movement_threshold:
            kept.append(item)
    if kept[-1] is not filtered[-1] and filtered[-1]["time_seconds"] > kept[-1]["time_seconds"]:
        kept.append(filtered[-1])
    return kept


def transform_for_focus(
    x_norm: float,
    y_norm: float,
    *,
    project_width: int,
    project_height: int,
    scale_percent: float,
    safe_margin: float = 0.08,
) -> dict[str, float]:
    if project_width <= 0 or project_height <= 0 or scale_percent <= 0:
        raise VisualError("project dimensions and scale must be positive")
    scale = scale_percent / 100.0
    width = project_width * scale
    height = project_height * scale
    focus_x = _clamp(x_norm, safe_margin, 1.0 - safe_margin)
    focus_y = _clamp(y_norm, safe_margin, 1.0 - safe_margin)
    x = project_width / 2.0 - focus_x * width
    y = project_height / 2.0 - focus_y * height

    # Avoid exposing empty canvas when panning a zoomed frame.
    min_x = project_width - width
    min_y = project_height - height
    x = _clamp(x, min_x, 0.0) if width >= project_width else (project_width - width) / 2.0
    y = _clamp(y, min_y, 0.0) if height >= project_height else (project_height - height) / 2.0
    return {
        "x": round(x, 3),
        "y": round(y, 3),
        "scale_percent": round(scale_percent, 3),
    }


def build_reframe_plan(
    samples: list[dict[str, float]],
    *,
    project_width: int,
    project_height: int,
    scale_percent: float,
    video_track_index: int = 0,
    smoothing: float = 0.35,
    min_interval: float = 0.8,
    movement_threshold: float = 0.08,
    confidence_threshold: float = 0.25,
    safe_margin: float = 0.08,
    title: str = "Smart reframe",
) -> dict[str, Any]:
    samples = simplify_track(
        smooth_track(samples, smoothing),
        min_interval=min_interval,
        movement_threshold=movement_threshold,
        confidence_threshold=confidence_threshold,
    )
    if not samples:
        raise VisualError("No usable subject samples")

    track_selector = {"audio": False, "index": video_track_index}
    steps: list[dict[str, Any]] = []

    # Cut at each new framing decision so each segment receives a native static
    # Transform effect. This avoids relying on unstable effect-keyframe schemas.
    for index, sample in enumerate(samples[1:], 1):
        steps.append(
            {
                "id": f"reframe-cut-{index:03d}",
                "tool": "kdenlive_cut_clip",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {
                            "track": track_selector,
                            "position_seconds": round(sample["time_seconds"], 6),
                        }
                    },
                    "position_seconds": round(sample["time_seconds"], 6),
                },
            }
        )

    # Apply transform to the segment covering each sample.
    for index, sample in enumerate(samples):
        next_time = samples[index + 1]["time_seconds"] if index + 1 < len(samples) else sample["time_seconds"] + max(min_interval, 0.25)
        probe_time = sample["time_seconds"] + max(0.001, min(0.05, (next_time - sample["time_seconds"]) / 2.0))
        transform = transform_for_focus(
            sample["x"],
            sample["y"],
            project_width=project_width,
            project_height=project_height,
            scale_percent=scale_percent,
            safe_margin=safe_margin,
        )
        steps.append(
            {
                "id": f"reframe-transform-{index:03d}",
                "tool": "kdenlive_set_transform",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {
                            "track": track_selector,
                            "position_seconds": round(probe_time, 6),
                        }
                    },
                    **transform,
                },
            }
        )
    steps.append({"id": "save-after-reframe", "tool": "kdenlive_save_project", "arguments": {}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": title,
            "generated_by": "Update P5 Visual Intelligence",
            "reframe_segments": len(samples),
            "project_width": project_width,
            "project_height": project_height,
            "scale_percent": scale_percent,
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-smart-reframe"},
        "steps": steps,
    }


def detect_faces_opencv(
    media: Path,
    *,
    sample_interval: float = 0.75,
    min_face_ratio: float = 0.04,
) -> list[dict[str, float]]:
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise VisualError(
            "OpenCV backend is optional. Install opencv-python or provide a subject-track JSON instead."
        ) from exc

    capture = cv2.VideoCapture(str(media))
    if not capture.isOpened():
        raise VisualError(f"OpenCV could not open {media}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        capture.release()
        raise VisualError("Could not determine media FPS")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, round(sample_interval * fps))
    cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        capture.release()
        raise VisualError("OpenCV face cascade is unavailable")

    samples: list[dict[str, float]] = []
    frame_index = 0
    while frame_index < total:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            break
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        if len(faces):
            x, y, w, h = max(faces, key=lambda r: int(r[2]) * int(r[3]))
            ratio = (float(w) * float(h)) / max(1.0, float(width * height))
            if ratio >= min_face_ratio:
                samples.append(
                    {
                        "time_seconds": frame_index / fps,
                        "x": (x + w / 2.0) / width,
                        "y": (y + h / 2.0) / height,
                        "confidence": _clamp(ratio / 0.20, 0.25, 1.0),
                    }
                )
        frame_index += step
    capture.release()
    if not samples:
        raise VisualError("No usable faces were detected")
    return samples


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 Edit Aja visual intelligence")
    sub = p.add_subparsers(dest="command", required=True)

    p_face = sub.add_parser("face-track", help="Create a normalized face track using optional OpenCV")
    p_face.add_argument("media", type=Path)
    p_face.add_argument("--sample-interval", type=float, default=0.75)
    p_face.add_argument("--min-face-ratio", type=float, default=0.04)
    p_face.add_argument("--output", type=Path, required=True)

    p_reframe = sub.add_parser("reframe", help="Create Phase 6 smart-reframe JSON from a subject track")
    p_reframe.add_argument("track", type=Path)
    p_reframe.add_argument("--preset", choices=tuple(PRESETS), default="vertical")
    p_reframe.add_argument("--project-width", type=int)
    p_reframe.add_argument("--project-height", type=int)
    p_reframe.add_argument("--scale-percent", type=float)
    p_reframe.add_argument("--video-track-index", type=int, default=0)
    p_reframe.add_argument("--smoothing", type=float, default=0.35)
    p_reframe.add_argument("--min-interval", type=float, default=0.8)
    p_reframe.add_argument("--movement-threshold", type=float, default=0.08)
    p_reframe.add_argument("--confidence-threshold", type=float, default=0.25)
    p_reframe.add_argument("--safe-margin", type=float, default=0.08)
    p_reframe.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "face-track":
            if not args.media.exists():
                raise VisualError(f"Media file not found: {args.media}")
            samples = detect_faces_opencv(
                args.media,
                sample_interval=args.sample_interval,
                min_face_ratio=args.min_face_ratio,
            )
            data = {"format": "update-p5-subject-track", "version": 1, "samples": samples}
        else:
            samples = load_track(args.track)
            preset_width, preset_height, preset_scale = PRESETS[args.preset]
            width = args.project_width or preset_width
            height = args.project_height or preset_height
            scale = args.scale_percent or preset_scale
            data = build_reframe_plan(
                samples,
                project_width=width,
                project_height=height,
                scale_percent=scale,
                video_track_index=args.video_track_index,
                smoothing=args.smoothing,
                min_interval=args.min_interval,
                movement_threshold=args.movement_threshold,
                confidence_threshold=args.confidence_threshold,
                safe_margin=args.safe_margin,
                title=f"Smart reframe ({args.preset})",
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (VisualError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

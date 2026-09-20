#!/usr/bin/env python3
"""Generic mask-based video effects for Update P5 Edit Aja.

Consumes update-p5-mask-track JSON from SAM 2 or another backend. It normalizes
the selected object's masks into a temporary image sequence, then uses FFmpeg
for background blur, object blur, background replacement, or transparent
foreground rendering. A Phase 6 insertion plan can be generated for the result.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class MaskEffectError(RuntimeError):
    pass


def _exe(name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise MaskEffectError(f"{name} was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise MaskEffectError(f"Could not execute {args[0]}: {exc}") from exc


def load_mask_object(path: Path, object_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MaskEffectError(f"Invalid mask-track JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != "update-p5-mask-track":
        raise MaskEffectError("Expected update-p5-mask-track JSON")
    objects = data.get("objects")
    if not isinstance(objects, list):
        raise MaskEffectError("Mask track has no objects array")
    obj = next((x for x in objects if isinstance(x, dict) and str(x.get("id")) == str(object_id)), None)
    if obj is None:
        raise MaskEffectError(f"Object id not found: {object_id}")
    return data, obj


def normalize_mask_sequence(obj: dict[str, Any], target_dir: Path) -> int:
    frames = obj.get("frames")
    if not isinstance(frames, list) or not frames:
        raise MaskEffectError("Selected object contains no mask frames")
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    expected = 0
    for item in sorted(
        (x for x in frames if isinstance(x, dict)),
        key=lambda x: int(x.get("frame_idx", -1)),
    ):
        frame_idx = int(item.get("frame_idx", -1))
        if frame_idx != expected:
            raise MaskEffectError(
                f"Mask sequence must be contiguous from frame 0; expected {expected}, got {frame_idx}"
            )
        source = Path(str(item.get("mask_path", "")))
        if not source.exists():
            raise MaskEffectError(f"Mask file not found: {source}")
        shutil.copy2(source, target_dir / f"{frame_idx:06d}.png")
        copied += 1
        expected += 1
    if copied == 0:
        raise MaskEffectError("No usable masks copied")
    return copied


def probe_geometry(video: Path, ffprobe: str) -> tuple[int, int]:
    proc = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            str(video),
        ]
    )
    if proc.returncode != 0:
        raise MaskEffectError(proc.stderr.strip() or "ffprobe geometry failed")
    try:
        w, h = proc.stdout.strip().split("x", 1)
        width, height = int(w), int(h)
    except (ValueError, TypeError) as exc:
        raise MaskEffectError(f"Invalid geometry from ffprobe: {proc.stdout!r}") from exc
    if width <= 0 or height <= 0:
        raise MaskEffectError("Video geometry must be positive")
    return width, height


def render_effect(
    video: Path,
    mask_pattern: Path,
    output: Path,
    *,
    fps: float,
    ffmpeg: str,
    mode: str,
    blur_radius: int = 18,
    background: Path | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    base = [
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
        str(mask_pattern),
    ]

    if mode == "foreground":
        graph = "[0:v][1:v]alphamerge,format=rgba[out]"
        args = base + [
            "-filter_complex", graph,
            "-map", "[out]",
            "-an",
            "-c:v", "qtrle",
            "-shortest",
            str(output),
        ]
    elif mode in {"background_blur", "object_blur"}:
        if blur_radius < 1:
            raise MaskEffectError("blur_radius must be >= 1")
        if mode == "background_blur":
            graph = (
                f"[0:v]split=2[orig][b];"
                f"[b]boxblur={blur_radius}:2[blurred];"
                "[blurred][orig][1:v]maskedmerge[out]"
            )
        else:
            graph = (
                f"[0:v]split=2[orig][b];"
                f"[b]boxblur={blur_radius}:2[blurred];"
                "[orig][blurred][1:v]maskedmerge[out]"
            )
        args = base + [
            "-filter_complex", graph,
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-c:a", "aac",
            "-shortest",
            str(output),
        ]
    elif mode == "replace_background":
        if background is None:
            raise MaskEffectError("replace_background requires a background image/video")
        if width is None or height is None:
            raise MaskEffectError("replace_background requires video width/height")
        args = base + [
            "-stream_loop", "-1",
            "-i", str(background),
            "-filter_complex",
            (
                f"[2:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}[bg];"
                "[bg][0:v][1:v]maskedmerge[out]"
            ),
            "-map", "[out]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-c:a", "aac",
            "-shortest",
            str(output),
        ]
    else:
        raise MaskEffectError(f"Unsupported mask effect mode: {mode}")

    proc = _run(args)
    if proc.returncode != 0:
        raise MaskEffectError(proc.stderr.strip() or f"FFmpeg {mode} effect failed")


def insertion_plan(asset: Path, *, at: float = 0.0, track_name: str = "AI Mask Effect") -> dict[str, Any]:
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "Mask effect asset",
            "generated_by": "Update P5 Mask Effects",
            "asset": str(asset.resolve()),
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-mask-effect"},
        "steps": [
            {"id": "maskfx-track", "tool": "kdenlive_add_track", "arguments": {"audio": False, "name": track_name}},
            {"id": "maskfx-import", "tool": "kdenlive_import_media", "arguments": {"path": str(asset.resolve())}},
            {
                "id": "maskfx-insert",
                "tool": "kdenlive_insert_bin_clip",
                "arguments": {
                    "bin_id": {"$ref": "maskfx-import.result.bin_id"},
                    "track_id": {"$ref": "maskfx-track.result.track_id"},
                    "position_seconds": at,
                    "use_targets": False,
                },
            },
            {"id": "maskfx-save", "tool": "kdenlive_save_project", "arguments": {}},
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Apply generic mask-based video effects")
    p.add_argument("video", type=Path)
    p.add_argument("mask_track", type=Path)
    p.add_argument("object_id")
    p.add_argument("--mode", choices=("foreground", "background_blur", "object_blur", "replace_background"), required=True)
    p.add_argument("--background", type=Path)
    p.add_argument("--blur-radius", type=int, default=18)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--plan-output", type=Path)
    p.add_argument("--at", type=float, default=0.0)
    p.add_argument("--ffmpeg")
    p.add_argument("--ffprobe")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.video.exists():
            raise MaskEffectError(f"Video not found: {args.video}")
        data, obj = load_mask_object(args.mask_track, args.object_id)
        fps = float(data.get("fps") or 0)
        if fps <= 0:
            raise MaskEffectError("Mask track does not contain a valid fps")
        ffmpeg = _exe("ffmpeg", args.ffmpeg)
        ffprobe = _exe("ffprobe", args.ffprobe)
        if args.background is not None and not args.background.exists():
            raise MaskEffectError(f"Background asset not found: {args.background}")
        width = height = None
        if args.mode == "replace_background":
            width, height = probe_geometry(args.video, ffprobe)
        with tempfile.TemporaryDirectory(prefix="update-p5-maskfx-") as td:
            root = Path(td)
            normalize_mask_sequence(obj, root)
            render_effect(
                args.video,
                root / "%06d.png",
                args.output,
                fps=fps,
                ffmpeg=ffmpeg,
                mode=args.mode,
                blur_radius=args.blur_radius,
                background=args.background,
                width=width,
                height=height,
            )
        print(f"Wrote {args.output}")
        if args.plan_output:
            plan = insertion_plan(args.output, at=args.at)
            args.plan_output.parent.mkdir(parents=True, exist_ok=True)
            args.plan_output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Wrote {args.plan_output}")
        return 0
    except (MaskEffectError, OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

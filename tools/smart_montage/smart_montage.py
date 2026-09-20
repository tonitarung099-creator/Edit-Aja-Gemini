#!/usr/bin/env python3
"""Smart beat-synced montage builder for Update P5 Edit Aja.

Compiles a list of B-roll/video/image assets plus Rhythm Intelligence beats into
native track/import/insert/resize/transform operations.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class MontageError(RuntimeError):
    pass


def load_beats(path: Path) -> list[dict[str, float]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MontageError(f"Invalid rhythm JSON: {exc}") from exc
    beats = None
    if isinstance(data, dict):
        audio = data.get("audio")
        if isinstance(audio, dict):
            beats = audio.get("beats")
        if beats is None:
            beats = data.get("beats")
    if not isinstance(beats, list):
        raise MontageError("Rhythm analysis contains no beats array")
    result = []
    for item in beats:
        if not isinstance(item, dict):
            continue
        try:
            time = float(item["time_seconds"])
            strength = float(item.get("strength", 0.0))
        except (KeyError, TypeError, ValueError):
            continue
        if time > 0:
            result.append({"time_seconds": time, "strength": strength})
    result.sort(key=lambda x: x["time_seconds"])
    if not result:
        raise MontageError("No usable beats found")
    return result


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MontageError(f"Invalid montage config JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MontageError("Montage config root must be an object")
    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        raise MontageError("Montage config requires a non-empty assets array")
    normalized = []
    for i, item in enumerate(assets):
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict) or not item.get("path"):
            raise MontageError(f"assets[{i}] must contain path")
        normalized.append(dict(item))
    data["assets"] = normalized
    return data


def select_boundaries(
    beats: list[dict[str, float]],
    *,
    start: float,
    end: float,
    every: int = 2,
    offset: int = 0,
    min_strength: float | None = None,
    min_segment: float = 0.35,
) -> list[float]:
    if end <= start:
        raise MontageError("end must be greater than start")
    if every < 1:
        raise MontageError("every must be >= 1")
    filtered = [
        beat["time_seconds"]
        for beat in beats
        if start < beat["time_seconds"] < end
        and (min_strength is None or beat["strength"] >= min_strength)
    ]
    selected = [t for i, t in enumerate(filtered) if (i - offset) % every == 0]
    boundaries = [start]
    for t in selected:
        if t - boundaries[-1] >= min_segment and end - t >= min_segment:
            boundaries.append(t)
    if end - boundaries[-1] < min_segment and len(boundaries) > 1:
        boundaries.pop()
    boundaries.append(end)
    return boundaries


def build_plan(
    assets: list[dict[str, Any]],
    boundaries: list[float],
    *,
    track_name: str = "Smart Montage",
    cycle_assets: bool = False,
    default_scale: float = 100.0,
) -> dict[str, Any]:
    intervals = list(zip(boundaries, boundaries[1:]))
    if not intervals:
        raise MontageError("No montage intervals")
    if not cycle_assets and len(assets) < len(intervals):
        intervals = intervals[: len(assets)]
    if not intervals:
        raise MontageError("No assets available for montage intervals")

    steps: list[dict[str, Any]] = [
        {
            "id": "montage-track",
            "tool": "kdenlive_add_track",
            "arguments": {"audio": False, "name": track_name},
        }
    ]
    used = []
    for i, (start, end) in enumerate(intervals):
        asset = assets[i % len(assets)] if cycle_assets else assets[i]
        path = str(asset["path"])
        duration = end - start
        prefix = f"montage-{i+1:03d}"
        steps.extend(
            [
                {
                    "id": f"{prefix}-import",
                    "tool": "kdenlive_import_media",
                    "arguments": {"path": path},
                },
                {
                    "id": f"{prefix}-insert",
                    "tool": "kdenlive_insert_bin_clip",
                    "arguments": {
                        "bin_id": {"$ref": f"{prefix}-import.result.bin_id"},
                        "track_id": {"$ref": "montage-track.result.track_id"},
                        "position_seconds": round(start, 6),
                        "use_targets": False,
                    },
                },
                {
                    "id": f"{prefix}-duration",
                    "tool": "kdenlive_resize_item",
                    "arguments": {
                        "item_id": {
                            "$clip_at": {
                                "track_id": {"$ref": "montage-track.result.track_id"},
                                "position_seconds": round(start + min(0.05, duration / 4.0), 6),
                            }
                        },
                        "duration_seconds": round(duration, 6),
                        "edge": "right",
                        "allow_single_resize": True,
                    },
                },
            ]
        )
        scale = float(asset.get("scale_percent", default_scale))
        x = asset.get("x")
        y = asset.get("y")
        if scale != 100.0 or x is not None or y is not None:
            args: dict[str, Any] = {
                "clip_id": {
                    "$clip_at": {
                        "track_id": {"$ref": "montage-track.result.track_id"},
                        "position_seconds": round(start + min(0.05, duration / 4.0), 6),
                    }
                },
                "scale_percent": scale,
            }
            if x is not None:
                args["x"] = float(x)
            if y is not None:
                args["y"] = float(y)
            steps.append({"id": f"{prefix}-transform", "tool": "kdenlive_set_transform", "arguments": args})
        used.append(
            {
                "path": path,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": duration,
            }
        )
    steps.append({"id": "save-after-montage", "tool": "kdenlive_save_project", "arguments": {}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "Smart beat-synced montage",
            "generated_by": "Update P5 Smart Montage",
            "clip_count": len(used),
            "clips": used,
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-smart-montage"},
        "steps": steps,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build beat-synced B-roll/image montages")
    p.add_argument("rhythm_analysis", type=Path)
    p.add_argument("config", type=Path)
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--every", type=int, default=2)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--min-strength", type=float)
    p.add_argument("--min-segment", type=float, default=0.35)
    p.add_argument("--cycle-assets", action="store_true")
    p.add_argument("--track-name", default="Smart Montage")
    p.add_argument("--default-scale", type=float, default=100.0)
    p.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        beats = load_beats(args.rhythm_analysis)
        config = load_config(args.config)
        boundaries = select_boundaries(
            beats,
            start=args.start,
            end=args.end,
            every=args.every,
            offset=args.offset,
            min_strength=args.min_strength,
            min_segment=args.min_segment,
        )
        plan = build_plan(
            config["assets"],
            boundaries,
            track_name=str(config.get("track_name", args.track_name)),
            cycle_assets=args.cycle_assets or bool(config.get("cycle_assets", False)),
            default_scale=float(config.get("default_scale", args.default_scale)),
        )
        plan["metadata"]["beat_selection"] = {
            "start": args.start,
            "end": args.end,
            "every": args.every,
            "offset": args.offset,
            "min_strength": args.min_strength,
            "boundary_count": len(boundaries),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output} ({plan['metadata']['clip_count']} montage clips)")
        return 0
    except (MontageError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

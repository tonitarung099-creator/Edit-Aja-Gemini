#!/usr/bin/env python3
"""Automatic music ducking planner for Update P5 Edit Aja.

Reads timestamped speech segments and generates native timeline cuts on the
music track, then lowers the volume of only the segments that overlap speech.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class DuckingError(RuntimeError):
    pass


def _load_segments(path: Path) -> list[dict[str, float]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DuckingError(f"Invalid transcript JSON: {exc}") from exc
    if isinstance(data, dict):
        for key in ("segments", "timeline_segments", "subtitles", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise DuckingError("Transcript must be a list or contain a segments array")
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start_seconds", item.get("start")))
            end = float(item.get("end_seconds", item.get("end")))
        except (TypeError, ValueError):
            continue
        if end > start:
            out.append({"start_seconds": start, "end_seconds": end})
    out.sort(key=lambda x: x["start_seconds"])
    if not out:
        raise DuckingError("Transcript contains no valid timestamped speech ranges")
    return out


def merge_speech_ranges(
    segments: list[dict[str, float]],
    *,
    lead: float = 0.18,
    tail: float = 0.25,
    merge_gap: float = 0.15,
    minimum_duration: float = 0.15,
) -> list[dict[str, float]]:
    ranges = [
        {
            "start_seconds": max(0.0, float(x["start_seconds"]) - lead),
            "end_seconds": float(x["end_seconds"]) + tail,
        }
        for x in segments
        if float(x["end_seconds"]) - float(x["start_seconds"]) >= minimum_duration
    ]
    if not ranges:
        return []
    ranges.sort(key=lambda x: x["start_seconds"])
    merged = [dict(ranges[0])]
    for item in ranges[1:]:
        prev = merged[-1]
        if item["start_seconds"] <= prev["end_seconds"] + merge_gap:
            prev["end_seconds"] = max(prev["end_seconds"], item["end_seconds"])
        else:
            merged.append(dict(item))
    return merged


def build_ducking_plan(
    ranges: list[dict[str, float]],
    *,
    music_track_index: int = 0,
    duck_gain_db: float = -14.0,
    title: str = "Auto duck music under speech",
) -> dict[str, Any]:
    if duck_gain_db > 0:
        raise DuckingError("duck_gain_db should normally be zero or negative")
    track = {"audio": True, "index": music_track_index}
    boundaries = sorted(
        {
            round(float(x["start_seconds"]), 6)
            for x in ranges
        }
        | {
            round(float(x["end_seconds"]), 6)
            for x in ranges
        }
    )
    steps: list[dict[str, Any]] = []
    for i, boundary in enumerate(boundaries, 1):
        steps.append(
            {
                "id": f"duck-cut-{i:03d}",
                "tool": "kdenlive_cut_clip",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {
                            "track": track,
                            "position_seconds": boundary,
                        }
                    },
                    "position_seconds": boundary,
                },
            }
        )
    for i, item in enumerate(ranges, 1):
        start = float(item["start_seconds"])
        end = float(item["end_seconds"])
        probe = start + min(0.05, max(0.001, (end - start) / 3.0))
        steps.append(
            {
                "id": f"duck-volume-{i:03d}",
                "tool": "kdenlive_set_clip_volume",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {
                            "track": track,
                            "position_seconds": round(probe, 6),
                        }
                    },
                    "gain_db": duck_gain_db,
                },
            }
        )
    steps.append({"id": "save-after-ducking", "tool": "kdenlive_save_project", "arguments": {}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": title,
            "generated_by": "Update P5 Auto Ducking",
            "speech_range_count": len(ranges),
            "duck_gain_db": duck_gain_db,
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-auto-ducking"},
        "steps": steps,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create native music ducking edits from speech timestamps")
    p.add_argument("transcript", type=Path)
    p.add_argument("--music-track-index", type=int, default=0)
    p.add_argument("--duck-gain-db", type=float, default=-14.0)
    p.add_argument("--lead", type=float, default=0.18)
    p.add_argument("--tail", type=float, default=0.25)
    p.add_argument("--merge-gap", type=float, default=0.15)
    p.add_argument("--minimum-duration", type=float, default=0.15)
    p.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        segments = _load_segments(args.transcript)
        ranges = merge_speech_ranges(
            segments,
            lead=args.lead,
            tail=args.tail,
            merge_gap=args.merge_gap,
            minimum_duration=args.minimum_duration,
        )
        if not ranges:
            raise DuckingError("No speech ranges remain after filtering")
        plan = build_ducking_plan(
            ranges,
            music_track_index=args.music_track_index,
            duck_gain_db=args.duck_gain_db,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output} ({len(ranges)} ducked speech ranges)")
        return 0
    except (DuckingError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

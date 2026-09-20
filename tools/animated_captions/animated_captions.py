#!/usr/bin/env python3
"""Animated/pop caption planner for Update P5 Edit Aja.

Builds short native title clips from word-level timestamps. Motion presets are
represented by several editable title segments with different Transform scales,
avoiding dependency on unstable effect-keyframe parameter layouts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class AnimatedCaptionError(RuntimeError):
    pass


PRESETS: dict[str, list[tuple[float, float]]] = {
    "clean": [(1.0, 100.0)],
    "pop": [(0.18, 86.0), (0.62, 112.0), (0.20, 100.0)],
    "punch": [(0.25, 122.0), (0.75, 104.0)],
    "bounce": [(0.16, 82.0), (0.34, 116.0), (0.25, 96.0), (0.25, 106.0)],
}


def load_words(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnimatedCaptionError(f"Invalid transcript JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("words")
    if not isinstance(data, list) or not data:
        raise AnimatedCaptionError("Animated captions require a non-empty words array")
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(item.get("text", "")).strip()
        if end > start and text:
            out.append({"start_seconds": start, "end_seconds": end, "text": text})
    if not out:
        raise AnimatedCaptionError("No valid timestamped words found")
    return out


def phase_segments(
    start: float,
    end: float,
    preset: str,
    *,
    minimum_phase: float = 0.035,
) -> list[dict[str, float]]:
    if preset not in PRESETS:
        raise AnimatedCaptionError(f"Unknown preset: {preset}")
    duration = end - start
    if duration <= 0:
        return []
    phases = PRESETS[preset]
    if len(phases) > 1 and duration < minimum_phase * len(phases):
        return [{"start_seconds": start, "end_seconds": end, "scale_percent": phases[1][1] if len(phases) > 1 else phases[0][1]}]
    out = []
    cursor = start
    for i, (fraction, scale) in enumerate(phases):
        phase_end = end if i == len(phases) - 1 else cursor + duration * fraction
        out.append({"start_seconds": cursor, "end_seconds": phase_end, "scale_percent": scale})
        cursor = phase_end
    return out


def build_plan(
    words: list[dict[str, Any]],
    *,
    preset: str = "pop",
    track_name: str = "Animated Captions",
    font: str = "",
    font_size: int = 78,
    font_color: str = "#FFFFFFFF",
    outline_color: str = "#000000FF",
    outline_width: int = 4,
    bold: bool = True,
    uppercase: bool = True,
    x: float = 760,
    y: float = 860,
    max_words: int | None = None,
) -> dict[str, Any]:
    if preset not in PRESETS:
        raise AnimatedCaptionError(f"Unknown preset: {preset}")
    if max_words is not None:
        words = words[:max_words]
    steps: list[dict[str, Any]] = [
        {
            "id": "animated-caption-track",
            "tool": "kdenlive_add_track",
            "arguments": {"audio": False, "name": track_name},
        }
    ]
    clip_count = 0
    for word_index, word in enumerate(words, 1):
        display = str(word["text"]).upper() if uppercase else str(word["text"])
        phases = phase_segments(float(word["start_seconds"]), float(word["end_seconds"]), preset)
        for phase_index, phase in enumerate(phases, 1):
            prefix = f"caption-{word_index:04d}-{phase_index:02d}"
            duration = float(phase["end_seconds"]) - float(phase["start_seconds"])
            title_args: dict[str, Any] = {
                "text": display,
                "name": f"Animated Caption - {display}",
                "duration_seconds": round(duration, 6),
                "track_id": {"$ref": "animated-caption-track.result.track_id"},
                "position_seconds": round(float(phase["start_seconds"]), 6),
                "font_size": font_size,
                "font_color": font_color,
                "outline_color": outline_color,
                "outline_width": outline_width,
                "bold": bold,
                "x": x,
                "y": y,
            }
            if font:
                title_args["font"] = font
            steps.append(
                {
                    "id": f"{prefix}-title",
                    "tool": "kdenlive_create_title",
                    "arguments": title_args,
                }
            )
            probe = float(phase["start_seconds"]) + min(0.01, max(0.001, duration / 4.0))
            steps.append(
                {
                    "id": f"{prefix}-scale",
                    "tool": "kdenlive_set_transform",
                    "arguments": {
                        "clip_id": {
                            "$clip_at": {
                                "track_id": {"$ref": "animated-caption-track.result.track_id"},
                                "position_seconds": round(probe, 6),
                            }
                        },
                        "scale_percent": float(phase["scale_percent"]),
                    },
                }
            )
            clip_count += 1
    steps.append({"id": "save-after-animated-captions", "tool": "kdenlive_save_project", "arguments": {}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": f"Animated captions ({preset})",
            "generated_by": "Update P5 Animated Captions",
            "preset": preset,
            "word_count": len(words),
            "title_clip_count": clip_count,
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-animated-captions"},
        "steps": steps,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create editable animated word captions")
    p.add_argument("transcript", type=Path)
    p.add_argument("--preset", choices=tuple(PRESETS), default="pop")
    p.add_argument("--track-name", default="Animated Captions")
    p.add_argument("--font", default="")
    p.add_argument("--font-size", type=int, default=78)
    p.add_argument("--font-color", default="#FFFFFFFF")
    p.add_argument("--outline-color", default="#000000FF")
    p.add_argument("--outline-width", type=int, default=4)
    p.add_argument("--no-bold", action="store_true")
    p.add_argument("--keep-case", action="store_true")
    p.add_argument("--x", type=float, default=760)
    p.add_argument("--y", type=float, default=860)
    p.add_argument("--max-words", type=int)
    p.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        words = load_words(args.transcript)
        plan = build_plan(
            words,
            preset=args.preset,
            track_name=args.track_name,
            font=args.font,
            font_size=args.font_size,
            font_color=args.font_color,
            outline_color=args.outline_color,
            outline_width=args.outline_width,
            bold=not args.no_bold,
            uppercase=not args.keep_case,
            x=args.x,
            y=args.y,
            max_words=args.max_words,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            f"Wrote {args.output} "
            f"({plan['metadata']['word_count']} words, {plan['metadata']['title_clip_count']} title clips)"
        )
        return 0
    except (AnimatedCaptionError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

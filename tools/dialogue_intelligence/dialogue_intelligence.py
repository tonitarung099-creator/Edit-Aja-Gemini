#!/usr/bin/env python3
"""Dialogue intelligence for Update P5 Edit Aja.

Analyzes timestamped transcript words to find filler words, immediate repeated
words and long gaps. It can emit a review report or a conservative Phase 6
remove-ranges plan.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_FILLERS = {
    "um", "umm", "uh", "uhh", "hmm", "hm", "erm", "er",
    "eee", "ee", "eh", "anu",
}


class DialogueError(RuntimeError):
    pass


def _norm(text: str) -> str:
    return re.sub(r"[^\w'-]+", "", text.lower(), flags=re.UNICODE)


def load_words(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DialogueError(f"Invalid transcript JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DialogueError("Transcript JSON root must be an object")
    words = data.get("words")
    if not isinstance(words, list) or not words:
        raise DialogueError(
            "Dialogue Intelligence needs word-level timestamps. "
            "Use the whisper.cpp adapter with JSON-full token timestamps."
        )
    result = []
    for item in words:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(item.get("text", "")).strip()
        if end > start and text:
            result.append({"start_seconds": start, "end_seconds": end, "text": text})
    result.sort(key=lambda x: x["start_seconds"])
    if not result:
        raise DialogueError("No valid timestamped words found")
    return result


def analyze_words(
    words: list[dict[str, Any]],
    *,
    fillers: set[str] | None = None,
    repeat_gap: float = 0.45,
    long_gap: float = 1.0,
) -> dict[str, Any]:
    fillers = fillers or DEFAULT_FILLERS
    filler_hits = []
    repeat_hits = []
    gaps = []
    prev: dict[str, Any] | None = None

    for item in words:
        token = _norm(str(item["text"]))
        if token in fillers:
            filler_hits.append(
                {
                    "start_seconds": item["start_seconds"],
                    "end_seconds": item["end_seconds"],
                    "text": item["text"],
                    "kind": "filler",
                }
            )
        if prev is not None:
            gap = float(item["start_seconds"]) - float(prev["end_seconds"])
            prev_token = _norm(str(prev["text"]))
            if token and token == prev_token and gap <= repeat_gap:
                repeat_hits.append(
                    {
                        "start_seconds": item["start_seconds"],
                        "end_seconds": item["end_seconds"],
                        "text": item["text"],
                        "kind": "repeat",
                    }
                )
            if gap >= long_gap:
                gaps.append(
                    {
                        "start_seconds": float(prev["end_seconds"]),
                        "end_seconds": float(item["start_seconds"]),
                        "duration_seconds": gap,
                        "kind": "long_gap",
                    }
                )
        prev = item

    return {
        "format": "update-p5-dialogue-analysis",
        "version": 1,
        "filler_words": filler_hits,
        "repeated_words": repeat_hits,
        "long_gaps": gaps,
        "summary": {
            "word_count": len(words),
            "filler_count": len(filler_hits),
            "repeat_count": len(repeat_hits),
            "long_gap_count": len(gaps),
        },
    }


def merge_ranges(ranges: list[dict[str, float]], gap: float = 0.06) -> list[dict[str, float]]:
    pairs = sorted(
        (float(r["start_seconds"]), float(r["end_seconds"]))
        for r in ranges
        if float(r["end_seconds"]) > float(r["start_seconds"])
    )
    if not pairs:
        return []
    out = [[pairs[0][0], pairs[0][1]]]
    for start, end in pairs[1:]:
        if start <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return [{"start_seconds": a, "end_seconds": b} for a, b in out]


def build_cut_ranges(
    analysis: dict[str, Any],
    *,
    remove_fillers: bool = True,
    remove_repeats: bool = True,
    shorten_gaps: bool = False,
    gap_keep: float = 0.35,
    padding: float = 0.02,
) -> list[dict[str, float]]:
    ranges: list[dict[str, float]] = []
    if remove_fillers:
        ranges.extend(
            {
                "start_seconds": max(0.0, float(x["start_seconds"]) - padding),
                "end_seconds": float(x["end_seconds"]) + padding,
            }
            for x in analysis.get("filler_words", [])
        )
    if remove_repeats:
        ranges.extend(
            {
                "start_seconds": max(0.0, float(x["start_seconds"]) - padding),
                "end_seconds": float(x["end_seconds"]) + padding,
            }
            for x in analysis.get("repeated_words", [])
        )
    if shorten_gaps:
        for item in analysis.get("long_gaps", []):
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
            if end - start > gap_keep:
                trim = (end - start) - gap_keep
                left = start + gap_keep / 2.0
                ranges.append({"start_seconds": left, "end_seconds": left + trim})
    return merge_ranges(ranges)


def to_ai_edit(
    ranges: list[dict[str, float]],
    *,
    video_track_index: int = 0,
    audio_track_index: int = 0,
) -> dict[str, Any]:
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "Dialogue cleanup",
            "generated_by": "Update P5 Dialogue Intelligence",
            "remove_range_count": len(ranges),
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-dialogue-cleanup"},
        "steps": [
            {
                "id": "dialogue-cleanup",
                "tool": "kdenlive_remove_ranges",
                "arguments": {
                    "track_ids": [
                        {"$track": {"audio": False, "index": video_track_index}},
                        {"$track": {"audio": True, "index": audio_track_index}},
                    ],
                    "ranges": [
                        {
                            "start_seconds": round(float(x["start_seconds"]), 6),
                            "end_seconds": round(float(x["end_seconds"]), 6),
                        }
                        for x in ranges
                    ],
                    "lift_only": False,
                    "dry_run": False,
                },
            },
            {"id": "save-after-dialogue-cleanup", "tool": "kdenlive_save_project", "arguments": {}},
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 dialogue intelligence")
    p.add_argument("transcript", type=Path)
    p.add_argument("--filler", action="append", default=[], help="Additional filler word; repeat option as needed")
    p.add_argument("--repeat-gap", type=float, default=0.45)
    p.add_argument("--long-gap", type=float, default=1.0)
    p.add_argument("--remove-fillers", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--remove-repeats", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--shorten-gaps", action="store_true")
    p.add_argument("--gap-keep", type=float, default=0.35)
    p.add_argument("--padding", type=float, default=0.02)
    p.add_argument("--video-track-index", type=int, default=0)
    p.add_argument("--audio-track-index", type=int, default=0)
    p.add_argument("--format", choices=("report", "ai-edit"), default="report")
    p.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        words = load_words(args.transcript)
        fillers = set(DEFAULT_FILLERS)
        fillers.update(_norm(x) for x in args.filler if _norm(x))
        analysis = analyze_words(words, fillers=fillers, repeat_gap=args.repeat_gap, long_gap=args.long_gap)
        if args.format == "report":
            data = analysis
        else:
            ranges = build_cut_ranges(
                analysis,
                remove_fillers=args.remove_fillers,
                remove_repeats=args.remove_repeats,
                shorten_gaps=args.shorten_gaps,
                gap_keep=args.gap_keep,
                padding=args.padding,
            )
            data = to_ai_edit(
                ranges,
                video_track_index=args.video_track_index,
                audio_track_index=args.audio_track_index,
            )
            data["metadata"]["dialogue_summary"] = analysis["summary"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (DialogueError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

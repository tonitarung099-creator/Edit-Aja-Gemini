#!/usr/bin/env python3
"""Audio intelligence for Update P5 Edit Aja.

Measures EBU-style loudness with FFmpeg loudnorm and creates a Phase 6 edit plan
that applies bounded clip gain plus optional native fades.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

LOUDNESS_JSON_RE = re.compile(r"\{\s*\"input_i\".*?\}", re.DOTALL)


class AudioError(RuntimeError):
    pass


def _binary(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if not found:
        raise AudioError("ffmpeg was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise AudioError(f"Could not execute {args[0]}: {exc}") from exc


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_loudness(text: str) -> dict[str, Any]:
    blocks = LOUDNESS_JSON_RE.findall(text)
    if not blocks:
        raise AudioError("FFmpeg output did not contain loudnorm JSON")
    try:
        raw = json.loads(blocks[-1])
    except json.JSONDecodeError as exc:
        raise AudioError("Invalid loudnorm JSON") from exc
    result: dict[str, Any] = {}
    for key, value in raw.items():
        numeric = _finite_float(value)
        result[key] = numeric if numeric is not None else value
    return result


def measure(path: Path, ffmpeg: str) -> dict[str, Any]:
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vn",
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode not in (0, 255):
        raise AudioError(proc.stderr.strip() or "FFmpeg loudness measurement failed")
    return parse_loudness(proc.stderr)


def recommend_gain(
    loudness: dict[str, Any],
    *,
    target_lufs: float = -16.0,
    true_peak_limit: float = -1.5,
    max_boost_db: float = 8.0,
    max_cut_db: float = 12.0,
) -> dict[str, float | bool | None]:
    integrated = _finite_float(loudness.get("input_i"))
    true_peak = _finite_float(loudness.get("input_tp"))
    if integrated is None:
        raise AudioError("Integrated loudness (input_i) is unavailable")

    desired = target_lufs - integrated
    if true_peak is not None:
        peak_headroom = true_peak_limit - true_peak
        desired = min(desired, peak_headroom)

    bounded = max(-abs(max_cut_db), min(abs(max_boost_db), desired))
    return {
        "input_lufs": integrated,
        "input_true_peak_db": true_peak,
        "target_lufs": target_lufs,
        "true_peak_limit_db": true_peak_limit,
        "unbounded_gain_db": desired,
        "recommended_gain_db": bounded,
        "limited_by_safety_bounds": not math.isclose(bounded, desired, abs_tol=1e-9),
    }


def build_plan(
    media: Path,
    recommendation: dict[str, Any],
    *,
    clip_time: float = 0.1,
    audio_track_index: int = 0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> dict[str, Any]:
    clip_selector = {
        "$clip_at": {
            "track": {"audio": True, "index": audio_track_index},
            "position_seconds": clip_time,
        }
    }
    steps: list[dict[str, Any]] = [
        {
            "id": "normalize-audio-gain",
            "tool": "kdenlive_set_clip_volume",
            "arguments": {
                "clip_id": clip_selector,
                "gain_db": round(float(recommendation["recommended_gain_db"]), 4),
            },
        }
    ]
    if fade_in > 0 or fade_out > 0:
        args: dict[str, Any] = {"clip_id": clip_selector}
        if fade_in > 0:
            args["fade_in_seconds"] = fade_in
        if fade_out > 0:
            args["fade_out_seconds"] = fade_out
        steps.append({"id": "audio-fades", "tool": "kdenlive_set_audio_fade", "arguments": args})
    steps.append({"id": "save-after-audio", "tool": "kdenlive_save_project", "arguments": {}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "Smart audio normalization",
            "generated_by": "Update P5 Audio Intelligence",
            "source_media": str(media.resolve()),
            "loudness": recommendation,
        },
        "safety": {
            "checkpoint": True,
            "checkpoint_label": "before-audio-normalization",
        },
        "steps": steps,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 Edit Aja audio intelligence")
    p.add_argument("media", type=Path)
    p.add_argument("--ffmpeg")
    p.add_argument("--target-lufs", type=float, default=-16.0)
    p.add_argument("--true-peak-limit", type=float, default=-1.5)
    p.add_argument("--max-boost-db", type=float, default=8.0)
    p.add_argument("--max-cut-db", type=float, default=12.0)
    p.add_argument("--output", type=Path)
    p.add_argument("--plan", action="store_true", help="Output Phase 6 AI Edit JSON instead of analysis JSON")
    p.add_argument("--clip-time", type=float, default=0.1)
    p.add_argument("--audio-track-index", type=int, default=0)
    p.add_argument("--fade-in", type=float, default=0.0)
    p.add_argument("--fade-out", type=float, default=0.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.media.exists():
            raise AudioError(f"Media file not found: {args.media}")
        ffmpeg = _binary(args.ffmpeg)
        loudness = measure(args.media, ffmpeg)
        rec = recommend_gain(
            loudness,
            target_lufs=args.target_lufs,
            true_peak_limit=args.true_peak_limit,
            max_boost_db=args.max_boost_db,
            max_cut_db=args.max_cut_db,
        )
        data: dict[str, Any]
        if args.plan:
            data = build_plan(
                args.media,
                rec,
                clip_time=args.clip_time,
                audio_track_index=args.audio_track_index,
                fade_in=args.fade_in,
                fade_out=args.fade_out,
            )
        else:
            data = {"loudness": loudness, "recommendation": rec}
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(f"Wrote {args.output}")
        else:
            print(text, end="")
        return 0
    except (AudioError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Media intelligence for Update P5 Edit Aja.

Uses FFmpeg/FFprobe already common in the editor toolchain. The module has no
third-party Python dependency. It can inspect media, detect silence, scene
changes and black frames, measure loudness, summarize pacing, and emit a Phase 6
AI Edit JSON smart-cut plan.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

FORMAT = "update-p5-media-analysis"
VERSION = 1

SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
SILENCE_END_RE = re.compile(
    r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(\d+(?:\.\d+)?)"
)
SCENE_TIME_RE = re.compile(r"\bpts_time:(-?\d+(?:\.\d+)?)")
BLACK_RE = re.compile(
    r"black_start:(-?\d+(?:\.\d+)?)\s+black_end:(-?\d+(?:\.\d+)?)\s+black_duration:(\d+(?:\.\d+)?)"
)


class MediaError(RuntimeError):
    pass


def _binary(name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise MediaError(f"Could not execute {args[0]}: {exc}") from exc


def probe_media(path: Path, ffprobe: str) -> dict[str, Any]:
    proc = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    if proc.returncode != 0:
        raise MediaError(proc.stderr.strip() or "ffprobe failed")
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned invalid JSON") from exc

    fmt = raw.get("format", {}) if isinstance(raw, dict) else {}
    streams = raw.get("streams", []) if isinstance(raw, dict) else []
    duration = _float_or_none(fmt.get("duration"))
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {
        "path": str(path.resolve()),
        "duration_seconds": duration,
        "size_bytes": _int_or_none(fmt.get("size")),
        "format_name": fmt.get("format_name"),
        "bit_rate": _int_or_none(fmt.get("bit_rate")),
        "video": _video_summary(video),
        "audio": _audio_summary(audio),
        "stream_count": len(streams),
    }


def _video_summary(stream: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stream:
        return None
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "pix_fmt": stream.get("pix_fmt"),
        "fps": _rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
        "duration_seconds": _float_or_none(stream.get("duration")),
    }


def _audio_summary(stream: dict[str, Any] | None) -> dict[str, Any] | None:
    if not stream:
        return None
    return {
        "codec": stream.get("codec_name"),
        "sample_rate": _int_or_none(stream.get("sample_rate")),
        "channels": stream.get("channels"),
        "channel_layout": stream.get("channel_layout"),
        "duration_seconds": _float_or_none(stream.get("duration")),
    }


def _rate(value: Any) -> float | None:
    if not value or not isinstance(value, str):
        return None
    if "/" not in value:
        return _float_or_none(value)
    left, right = value.split("/", 1)
    try:
        denominator = float(right)
        return None if denominator == 0 else float(left) / denominator
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_silencedetect(text: str, duration: float | None = None) -> list[dict[str, float]]:
    ranges: list[dict[str, float]] = []
    pending: float | None = None
    for line in text.splitlines():
        start = SILENCE_START_RE.search(line)
        if start:
            pending = max(0.0, float(start.group(1)))
        end = SILENCE_END_RE.search(line)
        if end:
            end_value = max(0.0, float(end.group(1)))
            parsed_duration = max(0.0, float(end.group(2)))
            start_value = pending if pending is not None else max(0.0, end_value - parsed_duration)
            if end_value > start_value:
                ranges.append(
                    {
                        "start_seconds": start_value,
                        "end_seconds": end_value,
                        "duration_seconds": end_value - start_value,
                    }
                )
            pending = None
    if pending is not None and duration is not None and duration > pending:
        ranges.append(
            {
                "start_seconds": pending,
                "end_seconds": duration,
                "duration_seconds": duration - pending,
            }
        )
    return ranges


def detect_silence(
    path: Path,
    ffmpeg: str,
    *,
    noise_db: float = -35.0,
    min_duration: float = 0.5,
    media_duration: float | None = None,
) -> list[dict[str, float]]:
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db:g}dB:d={min_duration:g}",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode not in (0, 255):
        raise MediaError(proc.stderr.strip() or "FFmpeg silencedetect failed")
    return parse_silencedetect(proc.stderr, media_duration)


def parse_scene_times(text: str) -> list[float]:
    times = []
    for line in text.splitlines():
        if "showinfo" not in line:
            continue
        match = SCENE_TIME_RE.search(line)
        if match:
            value = max(0.0, float(match.group(1)))
            if not times or abs(value - times[-1]) > 1e-4:
                times.append(value)
    return times


def detect_scenes(path: Path, ffmpeg: str, threshold: float = 0.35) -> list[float]:
    if not 0.0 < threshold < 1.0:
        raise MediaError("scene threshold must be between 0 and 1")
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            f"select='gt(scene,{threshold:g})',showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode not in (0, 255):
        raise MediaError(proc.stderr.strip() or "FFmpeg scene detection failed")
    return parse_scene_times(proc.stderr)


def parse_blackdetect(text: str) -> list[dict[str, float]]:
    ranges = []
    for match in BLACK_RE.finditer(text):
        start = max(0.0, float(match.group(1)))
        end = max(start, float(match.group(2)))
        ranges.append(
            {
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": end - start,
            }
        )
    return ranges


def detect_black(
    path: Path,
    ffmpeg: str,
    *,
    min_duration: float = 0.5,
    picture_threshold: float = 0.98,
) -> list[dict[str, float]]:
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-vf",
            f"blackdetect=d={min_duration:g}:pic_th={picture_threshold:g}",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode not in (0, 255):
        raise MediaError(proc.stderr.strip() or "FFmpeg blackdetect failed")
    return parse_blackdetect(proc.stderr)


def parse_loudnorm(text: str) -> dict[str, float | str | None]:
    blocks = re.findall(r"\{\s*\"input_i\".*?\}", text, flags=re.DOTALL)
    if not blocks:
        raise MediaError("Could not find loudnorm JSON in FFmpeg output")
    try:
        raw = json.loads(blocks[-1])
    except json.JSONDecodeError as exc:
        raise MediaError("Could not parse loudnorm JSON") from exc
    result: dict[str, float | str | None] = {}
    for key, value in raw.items():
        numeric = _float_or_none(value)
        result[key] = numeric if numeric is not None and math.isfinite(numeric) else value
    return result


def measure_loudness(path: Path, ffmpeg: str) -> dict[str, float | str | None]:
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode not in (0, 255):
        raise MediaError(proc.stderr.strip() or "FFmpeg loudness analysis failed")
    return parse_loudnorm(proc.stderr)


def scene_segments(cuts: list[float], duration: float | None) -> list[dict[str, float]]:
    if not duration or duration <= 0:
        return []
    boundaries = [0.0] + [t for t in sorted(set(cuts)) if 0 < t < duration] + [duration]
    segments = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end > start:
            segments.append(
                {
                    "start_seconds": start,
                    "end_seconds": end,
                    "duration_seconds": end - start,
                }
            )
    return segments


def pacing_summary(cuts: list[float], duration: float | None) -> dict[str, Any]:
    segments = scene_segments(cuts, duration)
    lengths = [s["duration_seconds"] for s in segments]
    if not lengths:
        return {
            "scene_count": 0,
            "cuts_per_minute": 0.0,
            "average_scene_seconds": None,
            "median_scene_seconds": None,
            "short_scene_count": 0,
            "long_scene_count": 0,
        }
    minutes = max((duration or 0.0) / 60.0, 1e-9)
    return {
        "scene_count": len(segments),
        "cuts_per_minute": len(cuts) / minutes,
        "average_scene_seconds": statistics.fmean(lengths),
        "median_scene_seconds": statistics.median(lengths),
        "short_scene_count": sum(1 for x in lengths if x < 2.0),
        "long_scene_count": sum(1 for x in lengths if x > 10.0),
        "segments": segments,
    }


def merge_ranges(ranges: list[dict[str, float]], *, gap: float = 0.0) -> list[dict[str, float]]:
    if not ranges:
        return []
    pairs = sorted(
        (
            max(0.0, float(r["start_seconds"])),
            max(0.0, float(r["end_seconds"])),
        )
        for r in ranges
        if float(r["end_seconds"]) > float(r["start_seconds"])
    )
    if not pairs:
        return []
    merged: list[list[float]] = [[pairs[0][0], pairs[0][1]]]
    for start, end in pairs[1:]:
        if start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [
        {"start_seconds": start, "end_seconds": end, "duration_seconds": end - start}
        for start, end in merged
    ]


def smart_cut_ranges(
    silences: list[dict[str, float]],
    *,
    duration: float | None,
    edge_keep: float = 0.12,
    min_remove: float = 0.35,
    keep_start: float = 0.0,
    keep_end: float = 0.0,
    merge_gap: float = 0.04,
) -> list[dict[str, float]]:
    candidates = []
    safe_end = None if duration is None else max(0.0, duration - keep_end)
    for item in silences:
        start = float(item["start_seconds"]) + edge_keep
        end = float(item["end_seconds"]) - edge_keep
        start = max(start, keep_start)
        if safe_end is not None:
            end = min(end, safe_end)
        if end - start >= min_remove:
            candidates.append({"start_seconds": start, "end_seconds": end})
    return merge_ranges(candidates, gap=merge_gap)


def build_smart_cut_plan(
    media_path: Path,
    ranges: list[dict[str, float]],
    *,
    title: str = "Smart silence cut",
    video_track_index: int = 0,
    audio_track_index: int | None = 0,
) -> dict[str, Any]:
    tracks: list[dict[str, Any]] = [{"$track": {"audio": False, "index": video_track_index}}]
    if audio_track_index is not None:
        tracks.append({"$track": {"audio": True, "index": audio_track_index}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": title,
            "generated_by": "Update P5 Media Intelligence",
            "source_media": str(media_path.resolve()),
        },
        "safety": {
            "checkpoint": True,
            "checkpoint_label": "before-smart-silence-cut",
        },
        "steps": [
            {
                "id": "smart-silence-cut",
                "tool": "kdenlive_remove_ranges",
                "note": "Generated from FFmpeg silencedetect analysis",
                "arguments": {
                    "track_ids": tracks,
                    "ranges": [
                        {
                            "start_seconds": round(float(r["start_seconds"]), 6),
                            "end_seconds": round(float(r["end_seconds"]), 6),
                        }
                        for r in ranges
                    ],
                    "lift_only": False,
                    "dry_run": False,
                },
            },
            {
                "id": "save-after-smart-cut",
                "tool": "kdenlive_save_project",
                "arguments": {},
            },
        ],
    }


def analyze(
    path: Path,
    ffmpeg: str,
    ffprobe: str,
    *,
    noise_db: float,
    silence_duration: float,
    scene_threshold: float,
    black_duration: float,
    black_threshold: float,
    include_loudness: bool,
) -> dict[str, Any]:
    probe = probe_media(path, ffprobe)
    duration = probe.get("duration_seconds")
    silence = detect_silence(
        path,
        ffmpeg,
        noise_db=noise_db,
        min_duration=silence_duration,
        media_duration=duration,
    )
    cuts = detect_scenes(path, ffmpeg, scene_threshold)
    black = detect_black(
        path,
        ffmpeg,
        min_duration=black_duration,
        picture_threshold=black_threshold,
    )
    result: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "media": probe,
        "silence": {
            "noise_db": noise_db,
            "minimum_duration_seconds": silence_duration,
            "ranges": silence,
            "total_seconds": sum(x["duration_seconds"] for x in silence),
        },
        "scenes": {
            "threshold": scene_threshold,
            "cut_times_seconds": cuts,
            "pacing": pacing_summary(cuts, duration),
        },
        "black_frames": {
            "minimum_duration_seconds": black_duration,
            "picture_threshold": black_threshold,
            "ranges": black,
            "total_seconds": sum(x["duration_seconds"] for x in black),
        },
    }
    if include_loudness and probe.get("audio"):
        result["loudness"] = measure_loudness(path, ffmpeg)
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 Edit Aja media intelligence")
    p.add_argument("--ffmpeg", help="FFmpeg executable path")
    p.add_argument("--ffprobe", help="FFprobe executable path")
    sub = p.add_subparsers(dest="command", required=True)

    def common(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("media", type=Path)
        cmd.add_argument("--noise-db", type=float, default=-35.0)
        cmd.add_argument("--silence-duration", type=float, default=0.5)
        cmd.add_argument("--scene-threshold", type=float, default=0.35)
        cmd.add_argument("--black-duration", type=float, default=0.5)
        cmd.add_argument("--black-threshold", type=float, default=0.98)

    p_analyze = sub.add_parser("analyze", help="Analyze media and emit a JSON report")
    common(p_analyze)
    p_analyze.add_argument("--no-loudness", action="store_true")
    p_analyze.add_argument("--output", type=Path)

    p_cut = sub.add_parser("smart-cut", help="Analyze silence and emit Phase 6 AI Edit JSON")
    common(p_cut)
    p_cut.add_argument("--edge-keep", type=float, default=0.12)
    p_cut.add_argument("--min-remove", type=float, default=0.35)
    p_cut.add_argument("--keep-start", type=float, default=0.0)
    p_cut.add_argument("--keep-end", type=float, default=0.0)
    p_cut.add_argument("--merge-gap", type=float, default=0.04)
    p_cut.add_argument("--video-track-index", type=int, default=0)
    p_cut.add_argument("--audio-track-index", type=int, default=0)
    p_cut.add_argument("--video-only", action="store_true")
    p_cut.add_argument("--output", type=Path, required=True)

    p_probe = sub.add_parser("probe", help="Print normalized media metadata")
    p_probe.add_argument("media", type=Path)
    return p


def _write_json(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"Wrote {output}")
    else:
        print(text, end="")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.media.exists():
            raise MediaError(f"Media file not found: {args.media}")
        ffprobe = _binary("ffprobe", args.ffprobe)
        if args.command == "probe":
            _write_json(probe_media(args.media, ffprobe), None)
            return 0

        ffmpeg = _binary("ffmpeg", args.ffmpeg)
        if args.command == "analyze":
            report = analyze(
                args.media,
                ffmpeg,
                ffprobe,
                noise_db=args.noise_db,
                silence_duration=args.silence_duration,
                scene_threshold=args.scene_threshold,
                black_duration=args.black_duration,
                black_threshold=args.black_threshold,
                include_loudness=not args.no_loudness,
            )
            _write_json(report, args.output)
            return 0

        probe = probe_media(args.media, ffprobe)
        silences = detect_silence(
            args.media,
            ffmpeg,
            noise_db=args.noise_db,
            min_duration=args.silence_duration,
            media_duration=probe.get("duration_seconds"),
        )
        ranges = smart_cut_ranges(
            silences,
            duration=probe.get("duration_seconds"),
            edge_keep=args.edge_keep,
            min_remove=args.min_remove,
            keep_start=args.keep_start,
            keep_end=args.keep_end,
            merge_gap=args.merge_gap,
        )
        plan = build_smart_cut_plan(
            args.media,
            ranges,
            video_track_index=args.video_track_index,
            audio_track_index=None if args.video_only else args.audio_track_index,
        )
        plan["metadata"]["analysis"] = {
            "silence_count": len(silences),
            "remove_range_count": len(ranges),
            "remove_seconds": sum(r["duration_seconds"] for r in ranges),
        }
        _write_json(plan, args.output)
        return 0
    except (MediaError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

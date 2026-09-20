#!/usr/bin/env python3
"""Rhythm intelligence for Update P5 Edit Aja.

Detects visual activity from low-resolution grayscale frame differences and
audio beats from short-time energy novelty. Uses FFmpeg plus Python stdlib only.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


class RhythmError(RuntimeError):
    pass


def _exe(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if not found:
        raise RhythmError("ffmpeg was not found in PATH")
    return found


def _run_bytes(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(args, capture_output=True, check=False)
    except OSError as exc:
        raise RhythmError(f"Could not execute {args[0]}: {exc}") from exc


def motion_samples(
    media: Path,
    ffmpeg: str,
    *,
    fps: float = 4.0,
    width: int = 160,
    height: int = 90,
) -> list[dict[str, float]]:
    if fps <= 0 or width <= 0 or height <= 0:
        raise RhythmError("fps/width/height must be positive")
    proc = _run_bytes(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media),
            "-an",
            "-vf",
            f"fps={fps:g},scale={width}:{height},format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ]
    )
    if proc.returncode != 0:
        raise RhythmError(proc.stderr.decode("utf-8", errors="replace").strip() or "FFmpeg motion extraction failed")
    frame_size = width * height
    data = proc.stdout
    frame_count = len(data) // frame_size
    if frame_count < 2:
        return []
    out = []
    prev = memoryview(data)[0:frame_size]
    for i in range(1, frame_count):
        cur = memoryview(data)[i * frame_size : (i + 1) * frame_size]
        total = 0
        for a, b in zip(prev, cur):
            total += abs(int(a) - int(b))
        score = total / (frame_size * 255.0)
        out.append({"time_seconds": i / fps, "motion_score": score})
        prev = cur
    return out


def activity_ranges(
    samples: list[dict[str, float]],
    *,
    threshold: float = 0.055,
    minimum_duration: float = 0.5,
    bridge_gap: float = 0.35,
) -> list[dict[str, float]]:
    if not samples:
        return []
    times = [float(x["time_seconds"]) for x in samples]
    step = statistics.median(
        [b - a for a, b in zip(times, times[1:]) if b > a]
    ) if len(times) > 1 else 0.25
    hot = [x for x in samples if float(x["motion_score"]) >= threshold]
    if not hot:
        return []
    raw = []
    start = prev = float(hot[0]["time_seconds"])
    peak = float(hot[0]["motion_score"])
    total = peak
    count = 1
    for item in hot[1:]:
        t = float(item["time_seconds"])
        score = float(item["motion_score"])
        if t - prev <= step + bridge_gap:
            prev = t
            peak = max(peak, score)
            total += score
            count += 1
        else:
            raw.append((start, prev + step, peak, total / count))
            start = prev = t
            peak = total = score
            count = 1
    raw.append((start, prev + step, peak, total / count))
    return [
        {
            "start_seconds": a,
            "end_seconds": b,
            "duration_seconds": b - a,
            "peak_motion": peak,
            "average_motion": avg,
        }
        for a, b, peak, avg in raw
        if b - a >= minimum_duration
    ]


def audio_samples(
    media: Path,
    ffmpeg: str,
    *,
    sample_rate: int = 22050,
) -> array.array:
    proc = _run_bytes(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-",
        ]
    )
    if proc.returncode != 0:
        raise RhythmError(proc.stderr.decode("utf-8", errors="replace").strip() or "FFmpeg audio extraction failed")
    samples = array.array("h")
    samples.frombytes(proc.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def energy_envelope(
    samples: array.array,
    *,
    sample_rate: int = 22050,
    window_ms: float = 46.4,
    hop_ms: float = 23.2,
) -> list[dict[str, float]]:
    window = max(32, round(sample_rate * window_ms / 1000.0))
    hop = max(16, round(sample_rate * hop_ms / 1000.0))
    out = []
    for start in range(0, max(0, len(samples) - window + 1), hop):
        chunk = samples[start : start + window]
        if not chunk:
            break
        mean_square = sum(float(x) * float(x) for x in chunk) / len(chunk)
        rms = math.sqrt(mean_square) / 32768.0
        out.append({"time_seconds": (start + window / 2) / sample_rate, "rms": rms})
    return out


def detect_beats(
    envelope: list[dict[str, float]],
    *,
    sensitivity: float = 1.6,
    min_interval: float = 0.22,
) -> list[dict[str, float]]:
    if len(envelope) < 3:
        return []
    novelty = [0.0]
    for prev, cur in zip(envelope, envelope[1:]):
        novelty.append(max(0.0, float(cur["rms"]) - float(prev["rms"])))
    positive = [x for x in novelty if x > 0]
    if not positive:
        return []
    median = statistics.median(positive)
    deviations = [abs(x - median) for x in positive]
    mad = statistics.median(deviations) if deviations else 0.0
    # If all strong onsets have the same novelty, MAD is zero. In that case
    # the median itself is the correct threshold; adding an epsilon would
    # incorrectly reject every identical beat.
    threshold = median + sensitivity * mad

    candidates = []
    for i in range(1, len(novelty) - 1):
        if novelty[i] >= threshold and novelty[i] >= novelty[i - 1] and novelty[i] >= novelty[i + 1]:
            candidates.append(
                {
                    "time_seconds": float(envelope[i]["time_seconds"]),
                    "strength": novelty[i],
                }
            )
    beats = []
    for item in candidates:
        if not beats or item["time_seconds"] - beats[-1]["time_seconds"] >= min_interval:
            beats.append(item)
        elif item["strength"] > beats[-1]["strength"]:
            beats[-1] = item
    if len(beats) >= 2:
        intervals = [
            b["time_seconds"] - a["time_seconds"]
            for a, b in zip(beats, beats[1:])
            if b["time_seconds"] > a["time_seconds"]
        ]
        bpm = 60.0 / statistics.median(intervals) if intervals else None
    else:
        bpm = None
    for item in beats:
        item["estimated_bpm"] = bpm
    return beats


def analyze(
    media: Path,
    ffmpeg: str,
    *,
    motion_fps: float,
    motion_threshold: float,
    beat_sensitivity: float,
    beat_min_interval: float,
) -> dict[str, Any]:
    motion = motion_samples(media, ffmpeg, fps=motion_fps)
    activity = activity_ranges(motion, threshold=motion_threshold)
    pcm = audio_samples(media, ffmpeg)
    env = energy_envelope(pcm)
    beats = detect_beats(env, sensitivity=beat_sensitivity, min_interval=beat_min_interval)
    bpm = beats[0].get("estimated_bpm") if beats else None
    return {
        "format": "update-p5-rhythm-analysis",
        "version": 1,
        "media": str(media.resolve()),
        "motion": {
            "sample_fps": motion_fps,
            "threshold": motion_threshold,
            "samples": motion,
            "activity_ranges": activity,
        },
        "audio": {
            "beats": beats,
            "estimated_bpm": bpm,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 motion/activity and beat detection")
    p.add_argument("media", type=Path)
    p.add_argument("--ffmpeg")
    p.add_argument("--motion-fps", type=float, default=4.0)
    p.add_argument("--motion-threshold", type=float, default=0.055)
    p.add_argument("--beat-sensitivity", type=float, default=1.6)
    p.add_argument("--beat-min-interval", type=float, default=0.22)
    p.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.media.exists():
            raise RhythmError(f"Media file not found: {args.media}")
        ffmpeg = _exe(args.ffmpeg)
        report = analyze(
            args.media,
            ffmpeg,
            motion_fps=args.motion_fps,
            motion_threshold=args.motion_threshold,
            beat_sensitivity=args.beat_sensitivity,
            beat_min_interval=args.beat_min_interval,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (RhythmError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

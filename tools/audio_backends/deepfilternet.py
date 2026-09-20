#!/usr/bin/env python3
"""Optional DeepFilterNet backend for Update P5 Edit Aja.

Uses the external deep-filter binary. Media is converted to a 48 kHz WAV,
enhanced, copied to a stable output path, and can be wrapped in a Phase 6 plan
that imports the cleaned audio while muting the original clip.
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


class DeepFilterError(RuntimeError):
    pass


def _exe(name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise DeepFilterError(f"{name} was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise DeepFilterError(f"Could not execute {args[0]}: {exc}") from exc


def convert_to_48k_wav(media: Path, wav: Path, ffmpeg: str) -> None:
    proc = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(media),
            "-vn",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ]
    )
    if proc.returncode != 0:
        raise DeepFilterError(proc.stderr.strip() or "FFmpeg conversion to 48 kHz WAV failed")


def find_enhanced_wav(out_dir: Path, input_wav: Path) -> Path:
    candidates = [
        p for p in out_dir.rglob("*.wav")
        if p.resolve() != input_wav.resolve() and p.is_file()
    ]
    if not candidates:
        raise DeepFilterError(f"DeepFilterNet did not create a WAV under {out_dir}")
    candidates.sort(key=lambda p: (p.stat().st_size, p.stat().st_mtime), reverse=True)
    return candidates[0]


def enhance(
    input_wav: Path,
    out_dir: Path,
    deep_filter: str,
    *,
    model: Path | None = None,
    postfilter: bool = False,
    compensate_delay: bool = True,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    args = [deep_filter, "-o", str(out_dir)]
    if model is not None:
        args += ["-m", str(model)]
    if postfilter:
        args.append("--pf")
    if compensate_delay:
        args.append("--compensate-delay")
    args.append(str(input_wav))
    proc = _run(args)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise DeepFilterError(detail or "deep-filter failed")
    return find_enhanced_wav(out_dir, input_wav)


def build_replace_audio_plan(
    cleaned_audio: Path,
    *,
    at: float = 0.0,
    original_audio_track_index: int = 0,
    mute_original: bool = True,
    new_track_name: str = "AI Clean Voice",
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "id": "clean-audio-track",
            "tool": "kdenlive_add_track",
            "arguments": {"audio": True, "name": new_track_name},
        },
        {
            "id": "clean-audio-import",
            "tool": "kdenlive_import_media",
            "arguments": {"path": str(cleaned_audio.resolve())},
        },
        {
            "id": "clean-audio-insert",
            "tool": "kdenlive_insert_bin_clip",
            "arguments": {
                "bin_id": {"$ref": "clean-audio-import.result.bin_id"},
                "track_id": {"$ref": "clean-audio-track.result.track_id"},
                "position_seconds": at,
                "use_targets": False,
            },
        },
    ]
    if mute_original:
        steps.append(
            {
                "id": "mute-original-audio",
                "tool": "kdenlive_set_clip_volume",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {
                            "track": {"audio": True, "index": original_audio_track_index},
                            "position_seconds": at + 0.05,
                        }
                    },
                    "gain_db": -100.0,
                },
            }
        )
    steps.append({"id": "save-after-clean-audio", "tool": "kdenlive_save_project", "arguments": {}})
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "DeepFilterNet clean voice",
            "generated_by": "Update P5 DeepFilterNet adapter",
            "cleaned_audio": str(cleaned_audio.resolve()),
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-clean-voice"},
        "steps": steps,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Optional DeepFilterNet backend for Update P5 Edit Aja")
    p.add_argument("media", type=Path)
    p.add_argument("--deep-filter", help="Path to the deep-filter binary")
    p.add_argument("--ffmpeg", help="Path to ffmpeg")
    p.add_argument("--model", type=Path, help="Optional DeepFilterNet model tar.gz")
    p.add_argument("--postfilter", action="store_true")
    p.add_argument("--no-compensate-delay", action="store_true")
    p.add_argument("--output-audio", type=Path, required=True)
    p.add_argument("--plan-output", type=Path)
    p.add_argument("--at", type=float, default=0.0)
    p.add_argument("--original-audio-track-index", type=int, default=0)
    p.add_argument("--keep-original-audio", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.media.exists():
            raise DeepFilterError(f"Media file not found: {args.media}")
        if args.model is not None and not args.model.exists():
            raise DeepFilterError(f"Model file not found: {args.model}")
        ffmpeg = _exe("ffmpeg", args.ffmpeg)
        deep_filter = _exe("deep-filter", args.deep_filter)
        with tempfile.TemporaryDirectory(prefix="update-p5-deepfilter-") as td:
            root = Path(td)
            wav = root / "source-48k.wav"
            out_dir = root / "enhanced"
            convert_to_48k_wav(args.media, wav, ffmpeg)
            enhanced = enhance(
                wav,
                out_dir,
                deep_filter,
                model=args.model,
                postfilter=args.postfilter,
                compensate_delay=not args.no_compensate_delay,
            )
            args.output_audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(enhanced, args.output_audio)
        print(f"Wrote cleaned audio: {args.output_audio}")
        if args.plan_output:
            plan = build_replace_audio_plan(
                args.output_audio,
                at=args.at,
                original_audio_track_index=args.original_audio_track_index,
                mute_original=not args.keep_original_audio,
            )
            args.plan_output.parent.mkdir(parents=True, exist_ok=True)
            args.plan_output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"Wrote edit plan: {args.plan_output}")
        return 0
    except (DeepFilterError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Optional whisper.cpp backend for Update P5 Edit Aja.

The adapter does not bundle whisper.cpp or model weights. It converts media to
16 kHz mono PCM WAV with FFmpeg, invokes whisper-cli with JSON-full output, then
normalizes timestamps for Caption Intelligence / Phase 6 AI Edit JSON.
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


class WhisperError(RuntimeError):
    pass


def _exe(name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise WhisperError(f"{name} was not found in PATH")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise WhisperError(f"Could not execute {args[0]}: {exc}") from exc


def convert_to_wav(media: Path, wav: Path, ffmpeg: str) -> None:
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
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ]
    )
    if proc.returncode != 0:
        raise WhisperError(proc.stderr.strip() or "FFmpeg audio conversion failed")


def run_whisper(
    wav: Path,
    model: Path,
    whisper_cli: str,
    output_base: Path,
    *,
    language: str = "auto",
    translate: bool = False,
    threads: int | None = None,
) -> Path:
    args = [
        whisper_cli,
        "-m",
        str(model),
        "-f",
        str(wav),
        "--output-json-full",
        "--output-file",
        str(output_base),
        "--no-prints",
    ]
    if language and language != "auto":
        args += ["-l", language]
    if translate:
        args += ["-tr"]
    if threads is not None and threads > 0:
        args += ["-t", str(threads)]
    proc = _run(args)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise WhisperError(detail or "whisper-cli failed")
    output = Path(str(output_base) + ".json")
    if not output.exists():
        raise WhisperError(f"whisper-cli did not create expected JSON: {output}")
    return output


def _seconds_from_offsets(obj: dict[str, Any]) -> tuple[float | None, float | None]:
    offsets = obj.get("offsets")
    if not isinstance(offsets, dict):
        return None, None
    try:
        return float(offsets["from"]) / 1000.0, float(offsets["to"]) / 1000.0
    except (KeyError, TypeError, ValueError):
        return None, None


def normalize_whisper_json(data: dict[str, Any]) -> dict[str, Any]:
    transcription = data.get("transcription")
    if not isinstance(transcription, list):
        raise WhisperError("whisper.cpp JSON has no transcription array")
    segments = []
    words = []
    for item in transcription:
        if not isinstance(item, dict):
            continue
        start, end = _seconds_from_offsets(item)
        text = str(item.get("text", "")).strip()
        if start is not None and end is not None and end > start and text:
            segment: dict[str, Any] = {
                "start_seconds": start,
                "end_seconds": end,
                "text": text,
            }
            if "speaker" in item:
                segment["speaker"] = item["speaker"]
            if "speaker_turn_next" in item:
                segment["speaker_turn_next"] = bool(item["speaker_turn_next"])
            segments.append(segment)

        tokens = item.get("tokens")
        if isinstance(tokens, list):
            for token in tokens:
                if not isinstance(token, dict):
                    continue
                t0, t1 = _seconds_from_offsets(token)
                token_text = str(token.get("text", ""))
                if t0 is None or t1 is None or t1 <= t0 or not token_text.strip():
                    continue
                words.append(
                    {
                        "start_seconds": t0,
                        "end_seconds": t1,
                        "text": token_text,
                        "probability": token.get("p"),
                    }
                )
    if not segments:
        raise WhisperError("whisper.cpp JSON contained no timestamped text segments")
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    return {
        "format": "update-p5-transcript",
        "version": 1,
        "engine": "whisper.cpp",
        "language": result.get("language", params.get("language")),
        "segments": segments,
        "words": words,
    }


def transcript_to_ai_edit(transcript: dict[str, Any], *, style: str = "Default", layer: int = 0) -> dict[str, Any]:
    segments = transcript.get("segments", [])
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "whisper.cpp subtitles",
            "generated_by": "Update P5 whisper.cpp adapter",
            "language": transcript.get("language"),
            "segment_count": len(segments),
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-whisper-subtitles"},
        "steps": [
            {
                "id": "whisper-subtitles",
                "tool": "kdenlive_add_subtitle_batch",
                "arguments": {"segments": segments, "layer": layer, "style": style},
            },
            {"id": "save-after-whisper", "tool": "kdenlive_save_project", "arguments": {}},
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Optional whisper.cpp backend for Update P5 Edit Aja")
    p.add_argument("media", type=Path)
    p.add_argument("--model", type=Path, required=True, help="Local ggml whisper.cpp model file")
    p.add_argument("--whisper-cli", help="Path to whisper-cli")
    p.add_argument("--ffmpeg", help="Path to ffmpeg")
    p.add_argument("--language", default="auto")
    p.add_argument("--translate", action="store_true")
    p.add_argument("--threads", type=int)
    p.add_argument("--format", choices=("transcript", "ai-edit"), default="transcript")
    p.add_argument("--style", default="Default")
    p.add_argument("--layer", type=int, default=0)
    p.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not args.media.exists():
            raise WhisperError(f"Media file not found: {args.media}")
        if not args.model.exists():
            raise WhisperError(f"Model file not found: {args.model}")
        whisper_cli = _exe("whisper-cli", args.whisper_cli)
        ffmpeg = _exe("ffmpeg", args.ffmpeg)
        with tempfile.TemporaryDirectory(prefix="update-p5-whisper-") as td:
            root = Path(td)
            wav = root / "audio.wav"
            output_base = root / "whisper"
            convert_to_wav(args.media, wav, ffmpeg)
            raw_path = run_whisper(
                wav,
                args.model,
                whisper_cli,
                output_base,
                language=args.language,
                translate=args.translate,
                threads=args.threads,
            )
            try:
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise WhisperError(f"Invalid whisper.cpp JSON: {exc}") from exc
            if not isinstance(raw, dict):
                raise WhisperError("whisper.cpp JSON root must be an object")
            transcript = normalize_whisper_json(raw)
        data = transcript if args.format == "transcript" else transcript_to_ai_edit(transcript, style=args.style, layer=args.layer)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            f"Wrote {args.output} "
            f"({len(transcript['segments'])} segments, {len(transcript['words'])} timestamped tokens)"
        )
        return 0
    except (WhisperError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Caption intelligence for Update P5 Edit Aja.

Converts SRT or timestamped transcript JSON into cleaner phrase captions or
word-by-word captions, then exports either SRT or Phase 6 AI Edit JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

TIME_RE = re.compile(r"^(\d+):(\d+):(\d+)[,.](\d+)$")
BLOCK_RE = re.compile(
    r"(?ms)^\s*(?:\d+\s*\n)?"
    r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)"
    r"(?:[^\n]*)\n(.*?)(?=\n\s*\n|\Z)"
)


class CaptionError(RuntimeError):
    pass


def parse_time(value: str) -> float:
    match = TIME_RE.match(value.strip())
    if not match:
        raise CaptionError(f"Invalid subtitle timestamp: {value!r}")
    hours, minutes, seconds, millis = match.groups()
    ms = int(millis.ljust(3, "0")[:3])
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + ms / 1000.0


def format_time(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_srt(text: str) -> list[dict[str, Any]]:
    segments = []
    for match in BLOCK_RE.finditer(text.replace("\r\n", "\n")):
        start = parse_time(match.group(1))
        end = parse_time(match.group(2))
        body = clean_text(match.group(3))
        if body and end > start:
            segments.append({"start_seconds": start, "end_seconds": end, "text": body})
    if not segments:
        raise CaptionError("No valid SRT subtitle blocks found")
    return segments


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_transcript_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("segments", "timeline_segments", "subtitles", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise CaptionError("Transcript JSON must be a list or contain a segments array")

    segments = []
    for item in data:
        if not isinstance(item, dict):
            continue
        start = _number(item.get("start_seconds", item.get("start")))
        end = _number(item.get("end_seconds", item.get("end")))
        text = clean_text(str(item.get("text", "")))
        if start is None or end is None or not text or end <= start:
            continue
        segments.append({"start_seconds": start, "end_seconds": end, "text": text})
    if not segments:
        raise CaptionError("Transcript JSON contains no valid timestamped segments")
    return segments


def load_segments(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(path.read_text(encoding="utf-8-sig"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaptionError(f"Invalid transcript JSON: {exc}") from exc
    return parse_transcript_json(data)


def transform_case(text: str, mode: str) -> str:
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return text.title()
    return text


def _chunks(words: list[str], max_words: int, max_chars: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for word in words:
        proposed = current + [word]
        if current and (len(proposed) > max_words or len(" ".join(proposed)) > max_chars):
            chunks.append(current)
            current = [word]
        else:
            current = proposed
    if current:
        chunks.append(current)
    return chunks


def _split_segment(
    segment: dict[str, Any],
    *,
    mode: str,
    max_words: int,
    max_chars: int,
    max_duration: float,
    case: str,
) -> list[dict[str, Any]]:
    start = float(segment["start_seconds"])
    end = float(segment["end_seconds"])
    words = clean_text(str(segment["text"])).split()
    if not words:
        return []

    if mode == "word":
        chunks = [[w] for w in words]
    else:
        duration_chunks = max(1, int((end - start + max_duration - 1e-9) // max_duration)) if max_duration > 0 else 1
        target_words = max(1, min(max_words, (len(words) + duration_chunks - 1) // duration_chunks))
        chunks = _chunks(words, target_words, max_chars)

    weights = [max(1, sum(len(w) for w in chunk)) for chunk in chunks]
    total_weight = sum(weights)
    duration = end - start
    result = []
    cursor = start
    for i, (chunk, weight) in enumerate(zip(chunks, weights)):
        chunk_duration = duration * weight / total_weight
        chunk_end = end if i == len(chunks) - 1 else cursor + chunk_duration
        result.append(
            {
                "start_seconds": cursor,
                "end_seconds": chunk_end,
                "text": transform_case(" ".join(chunk), case),
            }
        )
        cursor = chunk_end
    return result


def _merge_tiny(
    segments: list[dict[str, Any]],
    *,
    min_duration: float,
    max_chars: int,
    max_duration: float,
    max_gap: float,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    out: list[dict[str, Any]] = []
    for item in segments:
        current = dict(item)
        if out:
            prev = out[-1]
            gap = float(current["start_seconds"]) - float(prev["end_seconds"])
            combined_text = f"{prev['text']} {current['text']}".strip()
            combined_duration = float(current["end_seconds"]) - float(prev["start_seconds"])
            current_duration = float(current["end_seconds"]) - float(current["start_seconds"])
            if (
                current_duration < min_duration
                and gap <= max_gap
                and len(combined_text) <= max_chars
                and combined_duration <= max_duration
            ):
                prev["end_seconds"] = current["end_seconds"]
                prev["text"] = combined_text
                continue
        out.append(current)
    return out


def resegment(
    segments: list[dict[str, Any]],
    *,
    mode: str = "phrase",
    max_words: int = 5,
    max_chars: int = 32,
    min_duration: float = 0.3,
    max_duration: float = 2.2,
    merge_gap: float = 0.12,
    case: str = "keep",
) -> list[dict[str, Any]]:
    if max_words < 1 or max_chars < 1 or max_duration <= 0:
        raise CaptionError("max_words/max_chars/max_duration must be positive")
    expanded = []
    for segment in segments:
        expanded.extend(
            _split_segment(
                segment,
                mode=mode,
                max_words=max_words,
                max_chars=max_chars,
                max_duration=max_duration,
                case=case,
            )
        )
    return _merge_tiny(
        expanded,
        min_duration=min_duration,
        max_chars=max_chars,
        max_duration=max_duration,
        max_gap=merge_gap,
    )


def to_srt(segments: list[dict[str, Any]]) -> str:
    blocks = []
    for index, item in enumerate(segments, 1):
        blocks.append(
            f"{index}\n"
            f"{format_time(float(item['start_seconds']))} --> {format_time(float(item['end_seconds']))}\n"
            f"{item['text']}"
        )
    return "\n\n".join(blocks) + "\n"


def to_ai_edit(
    segments: list[dict[str, Any]],
    *,
    title: str,
    style: str,
    layer: int,
) -> dict[str, Any]:
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": title,
            "generated_by": "Update P5 Caption Intelligence",
            "caption_count": len(segments),
        },
        "safety": {
            "checkpoint": True,
            "checkpoint_label": "before-smart-captions",
        },
        "steps": [
            {
                "id": "smart-captions",
                "tool": "kdenlive_add_subtitle_batch",
                "arguments": {
                    "segments": [
                        {
                            "start_seconds": round(float(item["start_seconds"]), 6),
                            "end_seconds": round(float(item["end_seconds"]), 6),
                            "text": str(item["text"]),
                        }
                        for item in segments
                    ],
                    "layer": layer,
                    "style": style,
                },
            },
            {"id": "save-after-captions", "tool": "kdenlive_save_project", "arguments": {}},
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 Edit Aja caption intelligence")
    p.add_argument("input", type=Path, help="SRT or timestamped transcript JSON")
    p.add_argument("--mode", choices=("phrase", "word"), default="phrase")
    p.add_argument("--max-words", type=int, default=5)
    p.add_argument("--max-chars", type=int, default=32)
    p.add_argument("--min-duration", type=float, default=0.3)
    p.add_argument("--max-duration", type=float, default=2.2)
    p.add_argument("--merge-gap", type=float, default=0.12)
    p.add_argument("--case", choices=("keep", "upper", "lower", "title"), default="keep")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--format", choices=("ai-edit", "srt", "json"), default="ai-edit")
    p.add_argument("--style", default="Default", help="Kdenlive subtitle style name")
    p.add_argument("--layer", type=int, default=0)
    p.add_argument("--title", default="Smart captions")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        segments = load_segments(args.input)
        processed = resegment(
            segments,
            mode=args.mode,
            max_words=args.max_words,
            max_chars=args.max_chars,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            merge_gap=args.merge_gap,
            case=args.case,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.format == "srt":
            args.output.write_text(to_srt(processed), encoding="utf-8")
        elif args.format == "json":
            args.output.write_text(json.dumps(processed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        else:
            args.output.write_text(
                json.dumps(
                    to_ai_edit(processed, title=args.title, style=args.style, layer=args.layer),
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        print(f"Wrote {args.output} ({len(processed)} captions)")
        return 0
    except (CaptionError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

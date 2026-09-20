#!/usr/bin/env python3
"""Semantic-ish bad-take review for Update P5 Edit Aja.

This deterministic reviewer finds likely retakes/corrections from timestamped
transcript text. It does not auto-delete by default. Approved candidate IDs can
be compiled into a native Phase 6 remove-ranges plan.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class BadTakeError(RuntimeError):
    pass


CORRECTION_PATTERNS = [
    re.compile(r"\b(maksud\s+saya|maksudnya|bukan[, ]|eh\s+bukan|ralat|koreksi)\b", re.I),
    re.compile(r"\b(ulang(?:i)?|ulang\s+lagi|take\s+lagi|sekali\s+lagi)\b", re.I),
    re.compile(r"\b(sorry|maaf)\b", re.I),
    re.compile(r"\b(i\s+mean|rather|sorry|let\s+me\s+say\s+that\s+again|start\s+again)\b", re.I),
]

FILLER_START = re.compile(r"^\s*(?:eh+|eee+|uh+|um+|hmm+|anu)\b", re.I)
WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)


def _normalize(text: str) -> list[str]:
    return [x.lower() for x in WORD_RE.findall(text)]


def load_segments(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BadTakeError(f"Invalid transcript JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("segments", data.get("transcription"))
    if not isinstance(data, list):
        raise BadTakeError("Transcript must contain a segments array")
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start_seconds", item.get("start")))
            end = float(item.get("end_seconds", item.get("end")))
        except (TypeError, ValueError):
            continue
        text = str(item.get("text", "")).strip()
        if end > start and text:
            out.append({
                "source_index": i,
                "start_seconds": start,
                "end_seconds": end,
                "text": text,
                "speaker": item.get("speaker"),
            })
    out.sort(key=lambda x: x["start_seconds"])
    if not out:
        raise BadTakeError("No valid timestamped segments found")
    return out


def _prefix_overlap(a: str, b: str, max_words: int = 8) -> int:
    wa = _normalize(a)[:max_words]
    wb = _normalize(b)[:max_words]
    count = 0
    for x, y in zip(wa, wb):
        if x != y:
            break
        count += 1
    return count


def _ngram_repeat(a: str, b: str, n: int = 3) -> bool:
    wa = _normalize(a)
    wb = _normalize(b)
    if len(wa) < n or len(wb) < n:
        return False
    tail = tuple(wa[-n:])
    return tail in [tuple(wb[i:i+n]) for i in range(len(wb)-n+1)]


def review(
    segments: list[dict[str, Any]],
    *,
    nearby_gap: float = 2.0,
    short_take_seconds: float = 2.2,
    prefix_words: int = 3,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for i, seg in enumerate(segments):
        reasons = []
        score = 0.0
        text = seg["text"]

        for pattern in CORRECTION_PATTERNS:
            if pattern.search(text):
                reasons.append("correction_language")
                score += 0.55
                break

        if FILLER_START.search(text) and (seg["end_seconds"] - seg["start_seconds"]) <= short_take_seconds:
            reasons.append("filler_false_start")
            score += 0.25

        if i + 1 < len(segments):
            nxt = segments[i + 1]
            gap = nxt["start_seconds"] - seg["end_seconds"]
            if gap <= nearby_gap:
                overlap = _prefix_overlap(text, nxt["text"])
                if overlap >= prefix_words:
                    reasons.append(f"restarted_phrase_prefix_{overlap}")
                    score += min(0.6, 0.18 + overlap * 0.08)
                elif _ngram_repeat(text, nxt["text"], 3):
                    reasons.append("nearby_phrase_repeat")
                    score += 0.35

                current_words = _normalize(text)
                next_words = _normalize(nxt["text"])
                if (
                    len(current_words) <= 5
                    and len(next_words) >= max(4, len(current_words))
                    and current_words
                    and current_words[0] == next_words[0]
                ):
                    reasons.append("short_false_start_before_full_take")
                    score += 0.30

        if reasons:
            confidence = min(1.0, score)
            candidate_id = f"candidate-{len(candidates)+1:04d}"
            candidates.append({
                "id": candidate_id,
                "start_seconds": seg["start_seconds"],
                "end_seconds": seg["end_seconds"],
                "text": text,
                "speaker": seg.get("speaker"),
                "confidence": round(confidence, 3),
                "reasons": reasons,
                "recommended_action": "review_remove" if confidence >= 0.45 else "review",
                "source_index": seg["source_index"],
            })

    return {
        "format": "update-p5-bad-take-review",
        "version": 1,
        "candidates": candidates,
        "summary": {
            "segment_count": len(segments),
            "candidate_count": len(candidates),
            "high_confidence_count": sum(1 for x in candidates if x["confidence"] >= 0.65),
        },
    }


def load_approvals(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BadTakeError(f"Invalid approvals JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("approved", data.get("candidate_ids"))
    if not isinstance(data, list):
        raise BadTakeError("Approvals JSON must be an array or contain approved/candidate_ids")
    return {str(x) for x in data}


def to_ai_edit(
    report: dict[str, Any],
    approved: set[str],
    *,
    padding: float = 0.03,
    video_track_index: int = 0,
    audio_track_index: int = 0,
) -> dict[str, Any]:
    selected = [x for x in report.get("candidates", []) if x.get("id") in approved]
    ranges = []
    for item in selected:
        ranges.append({
            "start_seconds": max(0.0, float(item["start_seconds"]) - padding),
            "end_seconds": float(item["end_seconds"]) + padding,
        })
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": "Approved bad-take cleanup",
            "generated_by": "Update P5 Bad Take Review",
            "approved_candidate_count": len(selected),
            "approved_candidate_ids": [x["id"] for x in selected],
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-approved-bad-take-cleanup"},
        "steps": [
            {
                "id": "remove-approved-bad-takes",
                "tool": "kdenlive_remove_ranges",
                "arguments": {
                    "track_ids": [
                        {"$track": {"audio": False, "index": video_track_index}},
                        {"$track": {"audio": True, "index": audio_track_index}},
                    ],
                    "ranges": ranges,
                    "lift_only": False,
                    "dry_run": False,
                },
            },
            {"id": "save-after-bad-take-cleanup", "tool": "kdenlive_save_project", "arguments": {}},
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Review likely retakes/corrections in a timestamped transcript")
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("transcript", type=Path)
    scan.add_argument("--nearby-gap", type=float, default=2.0)
    scan.add_argument("--short-take-seconds", type=float, default=2.2)
    scan.add_argument("--prefix-words", type=int, default=3)
    scan.add_argument("--output", type=Path, required=True)

    apply = sub.add_parser("compile")
    apply.add_argument("review", type=Path)
    apply.add_argument("approvals", type=Path)
    apply.add_argument("--padding", type=float, default=0.03)
    apply.add_argument("--video-track-index", type=int, default=0)
    apply.add_argument("--audio-track-index", type=int, default=0)
    apply.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            segments = load_segments(args.transcript)
            data = review(
                segments,
                nearby_gap=args.nearby_gap,
                short_take_seconds=args.short_take_seconds,
                prefix_words=args.prefix_words,
            )
        else:
            try:
                report = json.loads(args.review.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise BadTakeError(f"Invalid review JSON: {exc}") from exc
            if not isinstance(report, dict) or report.get("format") != "update-p5-bad-take-review":
                raise BadTakeError("Expected update-p5-bad-take-review JSON")
            approved = load_approvals(args.approvals)
            data = to_ai_edit(
                report,
                approved,
                padding=args.padding,
                video_track_index=args.video_track_index,
                audio_track_index=args.audio_track_index,
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (BadTakeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

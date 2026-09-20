#!/usr/bin/env python3
"""Lightweight natural-language command interpreter for Update P5 Edit Aja.

No LLM is required for the normal path. The module normalizes Indonesian/English
editing shorthand, tolerates common typos, extracts deterministic intent, does
simple animation math, and routes only genuinely complex requests to heavier
AI/MCP paths.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

FORMAT = "update-p5-local-edit-command"
VERSION = 1

CANONICAL_WORDS = {
    "potong", "split", "cut", "belah", "pisah",
    "hapus", "delete", "remove", "buang",
    "scene", "clip", "track", "snapshot", "foto", "gambar",
    "zoom", "perbesar", "scale", "smooth", "halus",
    "menit", "detik", "playhead", "disini", "sini",
    "semua", "musik", "audio", "video", "subtitle", "caption",
    "transkrip", "noise", "vokal", "background", "latar",
    "silence", "jeda", "fade", "mute", "pindah", "geser",
}

DEFAULT_ALIASES = {
    "ptong": "potong",
    "ptng": "potong",
    "potng": "potong",
    "poton": "potong",
    "hpus": "hapus",
    "hps": "hapus",
    "sceen": "scene",
    "scne": "scene",
    "scn": "scene",
    "zom": "zoom",
    "zoim": "zoom",
    "snapshpt": "snapshot",
    "snapshoot": "snapshot",
    "snap": "snapshot",
    "mnit": "menit",
    "mnt": "menit",
    "dtk": "detik",
    "dtiik": "detik",
    "smoth": "smooth",
    "smooh": "smooth",
    "disni": "disini",
    "disini": "disini",
    "subtitel": "subtitle",
    "captin": "caption",
}

SPLIT_WORDS = {"potong", "split", "cut", "belah", "pisah"}
DELETE_WORDS = {"hapus", "delete", "remove", "buang"}
ZOOM_WORDS = {"zoom", "perbesar", "scale"}

LOCAL_TOOL_PATTERNS = (
    (("transkrip", "transcribe"), "whispercpp"),
    (("subtitle", "caption"), "caption-intelligence"),
    (("noise", "bersihkan suara", "clean voice"), "deepfilternet"),
    (("vokal", "stem", "pisahkan musik"), "demucs"),
    (("background", "latar belakang"), "sam2/mask-effects"),
    (("silence", "jeda diam", "bagian diam"), "media-intelligence"),
)

AI_MARKERS = (
    "berdasarkan isi",
    "menurut isi",
    "paling menarik",
    "bagian terbaik",
    "membosankan",
    "lebih engaging",
    "lebih menarik",
    "yang relevan",
    "sesuai narasi",
    "sesuai isi cerita",
    "jangan potong kalimat",
)

MCP_MARKERS = (
    "cari gambar online",
    "cari footage online",
    "download dari",
    "ambil dari internet",
    "search web",
    "cari di internet",
)


@dataclass
class ParsedCommand:
    route: str
    intent: str
    confidence: float
    original_text: str
    normalized_text: str
    corrections: List[Dict[str, Any]]
    parameters: Dict[str, Any]
    native_tool_hint: Optional[str] = None
    needs_confirmation: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["format"] = FORMAT
        data["version"] = VERSION
        return data


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\d+(?:[.,]\d+)?%?|\d+:\d+(?::\d+)?|[a-zA-Z_]+", text)


def _best_fuzzy(token: str, vocabulary: Iterable[str]) -> Tuple[str, float]:
    best = token
    score = 0.0
    for candidate in vocabulary:
        s = difflib.SequenceMatcher(None, token, candidate).ratio()
        if s > score:
            best, score = candidate, s
    return best, score


def normalize_text(text: str, aliases: Optional[Dict[str, str]] = None) -> Tuple[str, List[Dict[str, Any]]]:
    aliases_all = dict(DEFAULT_ALIASES)
    if aliases:
        aliases_all.update({str(k).lower(): str(v).lower() for k, v in aliases.items()})
    raw = _strip_accents(text.lower()).replace("di sini", "disini")
    tokens = _tokenize(raw)
    out: List[str] = []
    corrections: List[Dict[str, Any]] = []

    for token in tokens:
        if re.fullmatch(r"\d+(?:[.,]\d+)?%?|\d+:\d+(?::\d+)?", token):
            out.append(token.replace(",", "."))
            continue
        fixed = aliases_all.get(token)
        if fixed:
            out.append(fixed)
            if fixed != token:
                corrections.append({"from": token, "to": fixed, "score": 1.0, "source": "alias"})
            continue
        if token not in CANONICAL_WORDS and len(token) >= 4:
            candidate, score = _best_fuzzy(token, CANONICAL_WORDS)
            if score >= 0.78:
                out.append(candidate)
                corrections.append({
                    "from": token, "to": candidate,
                    "score": round(score, 3), "source": "fuzzy"
                })
                continue
        out.append(token)
    return " ".join(out), corrections


def _number(value: str) -> float:
    return float(value.replace(",", ".").replace("%", ""))


def _clock_to_seconds(value: str) -> float:
    parts = [float(x) for x in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(value)


def extract_explicit_time(text: str) -> Optional[Tuple[float, str]]:
    m = re.search(r"\b(\d+:\d+(?::\d+)?)\b", text)
    if m:
        return _clock_to_seconds(m.group(1)), "timecode"

    m = re.search(r"\bmenit\s+(\d+(?:\.\d+)?)\b", text)
    if not m:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s+menit\b", text)
    if m:
        return _number(m.group(1)) * 60.0, "minutes"

    m = re.search(r"\bdetik\s+(\d+(?:\.\d+)?)\b", text)
    if not m:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s+detik\b", text)
    if m:
        return _number(m.group(1)), "seconds"
    return None


def extract_reference_duration(text: str) -> Optional[float]:
    patterns = (
        r"\bselama\s+(\d+(?:\.\d+)?)\s+detik\b",
        r"\bdalam\s+(\d+(?:\.\d+)?)\s+detik\b",
        r"\b(\d+(?:\.\d+)?)\s+detik\b",
    )
    for pattern in patterns:
        matches = list(re.finditer(pattern, text))
        if matches:
            return _number(matches[-1].group(1))
    return None


def compute_zoom_keyframes(
    start_scale: float,
    target_scale: float,
    reference_duration: float,
    actual_duration: float,
    easing: str = "smooth",
) -> Dict[str, Any]:
    if reference_duration <= 0 or actual_duration <= 0:
        raise ValueError("durations must be > 0")

    active_duration = min(actual_duration, reference_duration)
    progress = active_duration / reference_duration
    end_scale = start_scale + (target_scale - start_scale) * progress
    end_scale = round(end_scale, 4)

    keyframes = [
        {"time": 0.0, "scale_percent": round(start_scale, 4), "easing": easing},
        {"time": round(active_duration, 4), "scale_percent": end_scale, "easing": easing},
    ]
    if actual_duration > reference_duration:
        keyframes.append({
            "time": round(actual_duration, 4),
            "scale_percent": round(target_scale, 4),
            "easing": "hold",
        })

    return {
        "start_scale_percent": start_scale,
        "target_scale_percent": target_scale,
        "reference_duration_seconds": reference_duration,
        "actual_duration_seconds": actual_duration,
        "end_scale_percent": end_scale,
        "reaches_target": actual_duration >= reference_duration,
        "hold_after_target": actual_duration > reference_duration,
        "keyframes": keyframes,
    }


def _parse_zoom(text: str, context: Dict[str, Any]) -> Optional[ParsedCommand]:
    tokens = set(text.split())
    if not (tokens & ZOOM_WORDS):
        return None

    target_kind = "selected_clip"
    if "semua" in tokens and ("snapshot" in tokens or "foto" in tokens or "gambar" in tokens):
        target_kind = "all_snapshots"
    elif "snapshot" in tokens or "foto" in tokens or "gambar" in tokens:
        target_kind = "selected_snapshot"

    pair = re.search(r"\b(\d+(?:\.\d+)?)%?\s+(?:ke|sampai|menuju)\s+(\d+(?:\.\d+)?)%?\b", text)
    if not pair:
        nums = [_number(x) for x in re.findall(r"\b\d+(?:\.\d+)?%?\b", text)]
        if nums:
            start_scale = float(context.get("current_scale_percent", 100.0))
            target_scale = nums[0]
        else:
            return None
    else:
        start_scale, target_scale = _number(pair.group(1)), _number(pair.group(2))

    reference = extract_reference_duration(text) or float(context.get("default_zoom_duration_seconds", 5.0))
    easing = "smooth" if ("smooth" in tokens or "halus" in tokens or target_kind != "selected_clip") else "linear"

    animations: List[Dict[str, Any]] = []
    if target_kind == "all_snapshots":
        for snap in context.get("snapshots", []):
            dur = float(snap.get("duration", 0))
            if dur > 0:
                item = compute_zoom_keyframes(start_scale, target_scale, reference, dur, easing)
                item["clip_id"] = snap.get("id")
                animations.append(item)
    else:
        dur = context.get("selected_clip_duration")
        if dur:
            item = compute_zoom_keyframes(start_scale, target_scale, reference, float(dur), easing)
            item["clip_id"] = context.get("selected_clip_id")
            animations.append(item)

    return ParsedCommand(
        route="local",
        intent="animate_scale",
        confidence=0.97 if pair else 0.84,
        original_text="",
        normalized_text=text,
        corrections=[],
        parameters={
            "target": target_kind,
            "start_scale_percent": start_scale,
            "target_scale_percent": target_scale,
            "reference_duration_seconds": reference,
            "short_clip_behavior": "proportional",
            "long_clip_behavior": "reach_target_then_hold",
            "easing": easing,
            "animations": animations,
        },
        native_tool_hint="kdenlive_set_transform_keyframes",
        reason="Deterministic animation math; no LLM required.",
    )


def _parse_split(text: str, context: Dict[str, Any]) -> Optional[ParsedCommand]:
    tokens = set(text.split())
    if not (tokens & SPLIT_WORDS):
        return None

    if "disini" in tokens or "playhead" in tokens or ("sini" in tokens and "di" in tokens):
        return ParsedCommand(
            route="local", intent="split", confidence=0.99,
            original_text="", normalized_text=text, corrections=[],
            parameters={"target": "playhead", "time_seconds": context.get("playhead_seconds")},
            native_tool_hint="kdenlive_cut_clip",
            reason="Split at current playhead."
        )

    explicit = extract_explicit_time(text)
    if explicit:
        seconds, source = explicit
        return ParsedCommand(
            route="local", intent="split", confidence=0.98,
            original_text="", normalized_text=text, corrections=[],
            parameters={"target": "timeline_time", "time_seconds": seconds, "time_source": source},
            native_tool_hint="kdenlive_cut_clip",
            reason="Explicit timeline time."
        )

    m = re.search(r"\b(?:potong|split|cut|belah|pisah)\s+(\d+(?:\.\d+)?)\b", text)
    if m:
        minutes = _number(m.group(1))
        return ParsedCommand(
            route="local", intent="split", confidence=0.84,
            original_text="", normalized_text=text, corrections=[],
            parameters={
                "target": "timeline_time", "time_seconds": minutes * 60.0,
                "time_source": "bare_number_assumed_minutes",
            },
            native_tool_hint="kdenlive_cut_clip",
            needs_confirmation=True,
            reason="Bare number after split defaults to minutes; UI should show the interpretation."
        )
    return None


def _parse_delete(text: str, context: Dict[str, Any]) -> Optional[ParsedCommand]:
    tokens = set(text.split())
    if not (tokens & DELETE_WORDS):
        return None

    scene_range = re.search(r"\bscene\s+(\d+)\s+(?:sampai|hingga|ke)\s+(\d+)\b", text)
    scene_one = re.search(r"\bscene\s+(\d+)\b", text)
    if scene_range or scene_one:
        start = int((scene_range or scene_one).group(1))
        end = int(scene_range.group(2)) if scene_range else start
        params: Dict[str, Any] = {"scene_start": start, "scene_end": end}
        scene_map = context.get("scenes") or {}
        ranges = []
        for idx in range(start, end + 1):
            item = scene_map.get(str(idx), scene_map.get(idx))
            if item:
                ranges.append({"scene": idx, "start": item.get("start"), "end": item.get("end")})
        if ranges:
            params["resolved_ranges"] = ranges
        return ParsedCommand(
            route="local", intent="delete_scene", confidence=0.99,
            original_text="", normalized_text=text, corrections=[],
            parameters=params,
            native_tool_hint="kdenlive_remove_ranges",
            reason="Scene index is deterministic; scene times can be resolved from local scene analysis."
        )

    if "clip" in tokens and ("ini" in tokens or context.get("selected_clip_id")):
        return ParsedCommand(
            route="local", intent="delete_selected_clip", confidence=0.97,
            original_text="", normalized_text=text, corrections=[],
            parameters={"clip_id": context.get("selected_clip_id")},
            native_tool_hint="kdenlive_delete_item",
            reason="Uses current timeline selection."
        )

    return ParsedCommand(
        route="local", intent="delete_ambiguous", confidence=0.45,
        original_text="", normalized_text=text, corrections=[],
        parameters={},
        needs_confirmation=True,
        reason="Delete target is ambiguous; UI should ask scene/clip/time."
    )


def _route_heavy(text: str) -> Optional[ParsedCommand]:
    for marker in MCP_MARKERS:
        if marker in text:
            return ParsedCommand(
                route="mcp", intent="external_research_or_asset_action", confidence=0.95,
                original_text="", normalized_text=text, corrections=[],
                parameters={"matched_marker": marker},
                needs_confirmation=True,
                reason="Request needs an external service/tool rather than the lightweight local parser."
            )
    for words, engine in LOCAL_TOOL_PATTERNS:
        if any(w in text for w in words):
            return ParsedCommand(
                route="local_tool", intent="specialized_local_processing", confidence=0.9,
                original_text="", normalized_text=text, corrections=[],
                parameters={"engine": engine},
                reason="Use the existing specialized local engine; no general LLM required."
            )
    for marker in AI_MARKERS:
        if marker in text:
            return ParsedCommand(
                route="ai", intent="semantic_edit_request", confidence=0.9,
                original_text="", normalized_text=text, corrections=[],
                parameters={"matched_marker": marker},
                needs_confirmation=True,
                reason="Semantic editorial judgement is better routed to the API/MCP AI agent."
            )
    return None


def interpret(
    text: str,
    context: Optional[Dict[str, Any]] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    context = context or {}
    normalized, corrections = normalize_text(text, aliases)

    parsed = _parse_zoom(normalized, context)
    if not parsed:
        parsed = _parse_split(normalized, context)
    if not parsed:
        parsed = _parse_delete(normalized, context)
    if not parsed:
        parsed = _route_heavy(normalized)
    if not parsed:
        parsed = ParsedCommand(
            route="ai", intent="unrecognized_or_complex", confidence=0.35,
            original_text="", normalized_text=normalized, corrections=[],
            parameters={},
            needs_confirmation=True,
            reason="No safe deterministic interpretation; hand off to configured API/MCP AI."
        )

    parsed.original_text = text
    parsed.normalized_text = normalized
    parsed.corrections = corrections
    return parsed.to_dict()


def _load_json(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Update P5 lightweight Local Edit Agent")
    parser.add_argument("command", nargs="+", help="Natural-language editing command")
    parser.add_argument("--context", help="Optional timeline context JSON")
    parser.add_argument("--aliases", help="Optional user alias JSON")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    command = " ".join(args.command)
    context = _load_json(args.context)
    aliases = _load_json(args.aliases)
    result = interpret(command, context=context, aliases=aliases)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

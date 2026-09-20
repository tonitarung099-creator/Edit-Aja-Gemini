#!/usr/bin/env python3
"""Documentary/creator toolkit for Update P5 Edit Aja.

Compiles common documentary editing patterns into Phase 6 AI Edit JSON using
native title, track, media, resize, cut and transform tools.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class DocumentaryError(RuntimeError):
    pass


def _safe_id(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "item"


def _header(title: str, generated_by: str = "Update P5 Documentary Toolkit") -> dict[str, Any]:
    return {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {"title": title, "generated_by": generated_by},
        "safety": {"checkpoint": True, "checkpoint_label": "before-documentary-toolkit"},
        "steps": [],
    }


def _video_track(prefix: str, name: str, position: int | None = None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    args: dict[str, Any] = {"audio": False, "name": name}
    if position is not None:
        args["position"] = position
    step_id = f"{prefix}-track"
    return (
        [{"id": step_id, "tool": "kdenlive_add_track", "arguments": args}],
        {"$ref": f"{step_id}.result.track_id"},
    )


def lower_third_steps(
    *,
    prefix: str,
    name: str,
    role: str,
    at: float,
    duration: float,
    font: str = "",
    font_size: int = 44,
    color: str = "#FFFFFFFF",
    x: float = 90,
    y: float = 820,
) -> list[dict[str, Any]]:
    steps, track = _video_track(prefix, "Lower Third")
    text = name if not role else f"{name}\n{role}"
    args: dict[str, Any] = {
        "text": text,
        "name": f"Lower Third - {name}",
        "duration_seconds": duration,
        "track_id": track,
        "position_seconds": at,
        "font_size": font_size,
        "font_color": color,
        "bold": True,
        "x": x,
        "y": y,
    }
    if font:
        args["font"] = font
    steps.append({"id": f"{prefix}-title", "tool": "kdenlive_create_title", "arguments": args})
    return steps


def chapter_card_steps(
    *,
    prefix: str,
    title: str,
    subtitle: str,
    at: float,
    duration: float,
    font_size: int = 78,
    color: str = "#FFFFFFFF",
    x: float = 160,
    y: float = 360,
) -> list[dict[str, Any]]:
    steps, track = _video_track(prefix, "Chapter Cards")
    text = title if not subtitle else f"{title}\n{subtitle}"
    steps.append(
        {
            "id": f"{prefix}-title",
            "tool": "kdenlive_create_title",
            "arguments": {
                "text": text,
                "name": f"Chapter - {title}",
                "duration_seconds": duration,
                "track_id": track,
                "position_seconds": at,
                "font_size": font_size,
                "font_color": color,
                "bold": True,
                "x": x,
                "y": y,
            },
        }
    )
    return steps


def quote_card_steps(
    *,
    prefix: str,
    quote: str,
    source: str,
    at: float,
    duration: float,
    font_size: int = 52,
    color: str = "#FFFFFFFF",
    x: float = 170,
    y: float = 350,
) -> list[dict[str, Any]]:
    steps, track = _video_track(prefix, "Quote Cards")
    text = f"“{quote}”" if quote else ""
    if source:
        text += f"\n— {source}"
    steps.append(
        {
            "id": f"{prefix}-title",
            "tool": "kdenlive_create_title",
            "arguments": {
                "text": text,
                "name": "Quote Card",
                "duration_seconds": duration,
                "track_id": track,
                "position_seconds": at,
                "font_size": font_size,
                "font_color": color,
                "italic": True,
                "x": x,
                "y": y,
            },
        }
    )
    return steps


def broll_steps(
    *,
    prefix: str,
    asset: str,
    at: float,
    duration: float,
    scale_percent: float = 100.0,
    track_name: str = "B-roll",
) -> list[dict[str, Any]]:
    steps, track = _video_track(prefix, track_name)
    import_id = f"{prefix}-import"
    insert_id = f"{prefix}-insert"
    steps.extend(
        [
            {
                "id": import_id,
                "tool": "kdenlive_import_media",
                "arguments": {"path": asset},
            },
            {
                "id": insert_id,
                "tool": "kdenlive_insert_bin_clip",
                "arguments": {
                    "bin_id": {"$ref": f"{import_id}.result.bin_id"},
                    "track_id": track,
                    "position_seconds": at,
                    "use_targets": False,
                },
            },
            {
                "id": f"{prefix}-duration",
                "tool": "kdenlive_resize_item",
                "arguments": {
                    "item_id": {
                        "$clip_at": {
                            "track_id": track,
                            "position_seconds": at + min(0.05, max(0.001, duration / 10.0)),
                        }
                    },
                    "duration_seconds": duration,
                    "edge": "right",
                    "allow_single_resize": True,
                },
            },
        ]
    )
    if scale_percent != 100.0:
        steps.append(
            {
                "id": f"{prefix}-transform",
                "tool": "kdenlive_set_transform",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {
                            "track_id": track,
                            "position_seconds": at + min(0.05, max(0.001, duration / 10.0)),
                        }
                    },
                    "scale_percent": scale_percent,
                },
            }
        )
    return steps


def placeholder_steps(
    *,
    prefix: str,
    label: str,
    at: float,
    duration: float,
    font_size: int = 42,
) -> list[dict[str, Any]]:
    steps, track = _video_track(prefix, "B-roll Placeholders")
    steps.append(
        {
            "id": f"{prefix}-placeholder",
            "tool": "kdenlive_create_title",
            "arguments": {
                "text": f"B-ROLL\n{label}",
                "name": f"B-roll placeholder - {label}",
                "duration_seconds": duration,
                "track_id": track,
                "position_seconds": at,
                "font_size": font_size,
                "font_color": "#FFFFFFFF",
                "outline_color": "#000000FF",
                "outline_width": 2,
                "bold": True,
                "x": 100,
                "y": 120,
            },
        }
    )
    return steps


def ken_burns_steps(
    *,
    prefix: str,
    asset: str,
    at: float,
    duration: float,
    segments: int = 8,
    start_scale: float = 105.0,
    end_scale: float = 125.0,
    start_x: float = 0.50,
    start_y: float = 0.50,
    end_x: float = 0.55,
    end_y: float = 0.48,
    project_width: int = 1920,
    project_height: int = 1080,
) -> list[dict[str, Any]]:
    if duration <= 0 or segments < 1:
        raise DocumentaryError("Ken Burns duration must be positive and segments >= 1")
    steps = broll_steps(prefix=prefix, asset=asset, at=at, duration=duration, track_name="Ken Burns")
    track = {"$ref": f"{prefix}-track.result.track_id"}
    segment_duration = duration / segments

    for i in range(1, segments):
        cut_time = at + i * segment_duration
        steps.append(
            {
                "id": f"{prefix}-cut-{i:03d}",
                "tool": "kdenlive_cut_clip",
                "arguments": {
                    "clip_id": {
                        "$clip_at": {"track_id": track, "position_seconds": round(cut_time, 6)}
                    },
                    "position_seconds": round(cut_time, 6),
                },
            }
        )

    for i in range(segments):
        fraction = 0.0 if segments == 1 else i / (segments - 1)
        scale = start_scale + (end_scale - start_scale) * fraction
        focus_x = start_x + (end_x - start_x) * fraction
        focus_y = start_y + (end_y - start_y) * fraction
        width = project_width * scale / 100.0
        height = project_height * scale / 100.0
        x = project_width / 2.0 - focus_x * width
        y = project_height / 2.0 - focus_y * height
        x = max(project_width - width, min(0.0, x)) if width >= project_width else (project_width - width) / 2.0
        y = max(project_height - height, min(0.0, y)) if height >= project_height else (project_height - height) / 2.0
        probe = at + i * segment_duration + min(0.03, segment_duration / 4.0)
        steps.append(
            {
                "id": f"{prefix}-motion-{i:03d}",
                "tool": "kdenlive_set_transform",
                "arguments": {
                    "clip_id": {"$clip_at": {"track_id": track, "position_seconds": round(probe, 6)}},
                    "x": round(x, 3),
                    "y": round(y, 3),
                    "scale_percent": round(scale, 3),
                },
            }
        )
    return steps


def compile_config(data: dict[str, Any]) -> dict[str, Any]:
    operations = data.get("operations")
    if not isinstance(operations, list) or not operations:
        raise DocumentaryError("Config requires a non-empty operations array")
    plan = _header(str(data.get("title", "Documentary edit package")))
    for index, operation in enumerate(operations, 1):
        if not isinstance(operation, dict):
            raise DocumentaryError(f"operations[{index - 1}] must be an object")
        kind = str(operation.get("type", ""))
        prefix = f"doc-{index:03d}-{_safe_id(kind)}"
        common = dict(operation)
        common.pop("type", None)
        common["prefix"] = prefix
        if kind == "lower_third":
            plan["steps"].extend(lower_third_steps(**common))
        elif kind == "chapter_card":
            plan["steps"].extend(chapter_card_steps(**common))
        elif kind == "quote_card":
            plan["steps"].extend(quote_card_steps(**common))
        elif kind == "broll":
            plan["steps"].extend(broll_steps(**common))
        elif kind == "broll_placeholder":
            plan["steps"].extend(placeholder_steps(**common))
        elif kind == "ken_burns":
            plan["steps"].extend(ken_burns_steps(**common))
        else:
            raise DocumentaryError(f"Unsupported documentary operation type: {kind!r}")
    plan["steps"].append({"id": "documentary-save", "tool": "kdenlive_save_project", "arguments": {}})
    plan["metadata"]["operation_count"] = len(operations)
    return plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Update P5 Edit Aja documentary toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="Compile a documentary config to Phase 6 AI Edit JSON")
    p_compile.add_argument("config", type=Path)
    p_compile.add_argument("--output", type=Path, required=True)

    p_placeholder = sub.add_parser("placeholder", help="Create one B-roll placeholder")
    p_placeholder.add_argument("label")
    p_placeholder.add_argument("--at", type=float, required=True)
    p_placeholder.add_argument("--duration", type=float, default=4.0)
    p_placeholder.add_argument("--output", type=Path, required=True)

    p_ken = sub.add_parser("ken-burns", help="Create an editable Ken Burns photo plan")
    p_ken.add_argument("asset")
    p_ken.add_argument("--at", type=float, required=True)
    p_ken.add_argument("--duration", type=float, default=5.0)
    p_ken.add_argument("--segments", type=int, default=8)
    p_ken.add_argument("--start-scale", type=float, default=105.0)
    p_ken.add_argument("--end-scale", type=float, default=125.0)
    p_ken.add_argument("--output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compile":
            try:
                data = json.loads(args.config.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise DocumentaryError(f"Invalid documentary config JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise DocumentaryError("Documentary config must be one JSON object")
            plan = compile_config(data)
        elif args.command == "placeholder":
            plan = _header("B-roll placeholder")
            plan["steps"].extend(
                placeholder_steps(prefix="placeholder", label=args.label, at=args.at, duration=args.duration)
            )
            plan["steps"].append({"id": "save", "tool": "kdenlive_save_project", "arguments": {}})
        else:
            plan = _header("Ken Burns")
            plan["steps"].extend(
                ken_burns_steps(
                    prefix="ken-burns",
                    asset=args.asset,
                    at=args.at,
                    duration=args.duration,
                    segments=args.segments,
                    start_scale=args.start_scale,
                    end_scale=args.end_scale,
                )
            )
            plan["steps"].append({"id": "save", "tool": "kdenlive_save_project", "arguments": {}})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output} ({len(plan['steps'])} steps)")
        return 0
    except (DocumentaryError, OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Documentary graphics generator for Update P5 Edit Aja.

Generates SVG assets (supported by Kdenlive/MLT) for charts, timelines and map
overlays, plus an optional Phase 6 plan that inserts the assets on native tracks.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import mimetypes
import sys
from pathlib import Path
from typing import Any


class GraphicsError(RuntimeError):
    pass


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def svg_shell(width: int, height: int, body: str, background: str = "transparent") -> str:
    bg = "" if background == "transparent" else f'<rect width="100%" height="100%" fill="{esc(background)}"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{bg}{body}</svg>\n'
    )


def bar_chart(
    title: str,
    items: list[dict[str, Any]],
    *,
    width: int = 1920,
    height: int = 1080,
    background: str = "#101114",
    foreground: str = "#F5F5F5",
    accent: str = "#68A7FF",
) -> str:
    if not items:
        raise GraphicsError("bar chart requires at least one item")
    values = [float(x["value"]) for x in items]
    maximum = max(values)
    if maximum <= 0:
        raise GraphicsError("bar chart values must contain a positive value")
    left, right, top, bottom = 180, 120, 210, 150
    chart_w = width - left - right
    chart_h = height - top - bottom
    gap = 26
    bar_h = max(18, (chart_h - gap * (len(items) - 1)) / len(items))
    body = [
        f'<text x="{left}" y="110" fill="{esc(foreground)}" font-size="64" font-family="sans-serif" font-weight="700">{esc(title)}</text>'
    ]
    for i, item in enumerate(items):
        y = top + i * (bar_h + gap)
        value = float(item["value"])
        w = chart_w * max(0.0, value) / maximum
        label = item.get("label", "")
        display = item.get("display", f"{value:g}")
        body.extend(
            [
                f'<text x="{left}" y="{y + bar_h * 0.72:.2f}" fill="{esc(foreground)}" font-size="34" font-family="sans-serif">{esc(label)}</text>',
                f'<rect x="{left + 360}" y="{y:.2f}" width="{max(2,w-360):.2f}" height="{bar_h:.2f}" rx="12" fill="{esc(accent)}"/>',
                f'<text x="{min(width-180,left + 380 + max(2,w-360)):.2f}" y="{y + bar_h * 0.72:.2f}" fill="{esc(foreground)}" font-size="32" font-family="sans-serif" font-weight="700">{esc(display)}</text>',
            ]
        )
    return svg_shell(width, height, "".join(body), background)


def line_chart(
    title: str,
    points: list[dict[str, Any]],
    *,
    width: int = 1920,
    height: int = 1080,
    background: str = "#101114",
    foreground: str = "#F5F5F5",
    accent: str = "#68A7FF",
) -> str:
    if len(points) < 2:
        raise GraphicsError("line chart requires at least two points")
    values = [float(x["value"]) for x in points]
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        hi = lo + 1.0
    left, right, top, bottom = 180, 120, 220, 170
    chart_w = width - left - right
    chart_h = height - top - bottom
    coords = []
    for i, point in enumerate(points):
        x = left + chart_w * i / (len(points) - 1)
        y = top + chart_h * (hi - float(point["value"])) / (hi - lo)
        coords.append((x, y))
    path = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
    body = [
        f'<text x="{left}" y="110" fill="{esc(foreground)}" font-size="64" font-family="sans-serif" font-weight="700">{esc(title)}</text>',
        f'<line x1="{left}" y1="{top+chart_h}" x2="{left+chart_w}" y2="{top+chart_h}" stroke="{esc(foreground)}" stroke-opacity=".35" stroke-width="3"/>',
        f'<polyline points="{path}" fill="none" stroke="{esc(accent)}" stroke-width="12" stroke-linejoin="round" stroke-linecap="round"/>',
    ]
    for i, (point, (x, y)) in enumerate(zip(points, coords)):
        body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="12" fill="{esc(accent)}"/>')
        label = point.get("label", str(i + 1))
        body.append(
            f'<text x="{x:.2f}" y="{top+chart_h+60}" text-anchor="middle" fill="{esc(foreground)}" font-size="28" font-family="sans-serif">{esc(label)}</text>'
        )
    return svg_shell(width, height, "".join(body), background)


def timeline_graphic(
    title: str,
    events: list[dict[str, Any]],
    *,
    width: int = 1920,
    height: int = 1080,
    background: str = "#101114",
    foreground: str = "#F5F5F5",
    accent: str = "#68A7FF",
) -> str:
    if not events:
        raise GraphicsError("timeline requires at least one event")
    events = sorted(events, key=lambda x: float(x.get("position", x.get("year", 0))))
    axis_y = height / 2
    left, right = 160, 160
    body = [
        f'<text x="{left}" y="110" fill="{esc(foreground)}" font-size="64" font-family="sans-serif" font-weight="700">{esc(title)}</text>',
        f'<line x1="{left}" y1="{axis_y}" x2="{width-right}" y2="{axis_y}" stroke="{esc(foreground)}" stroke-opacity=".45" stroke-width="6"/>',
    ]
    for i, event in enumerate(events):
        x = left + (width - left - right) * (i / max(1, len(events) - 1))
        up = i % 2 == 0
        stem = 150
        text_y = axis_y - stem - 55 if up else axis_y + stem + 45
        year = event.get("label", event.get("year", event.get("position", "")))
        desc = event.get("text", "")
        body.extend(
            [
                f'<circle cx="{x:.2f}" cy="{axis_y:.2f}" r="18" fill="{esc(accent)}"/>',
                f'<line x1="{x:.2f}" y1="{axis_y:.2f}" x2="{x:.2f}" y2="{axis_y + (-stem if up else stem):.2f}" stroke="{esc(accent)}" stroke-width="5"/>',
                f'<text x="{x:.2f}" y="{text_y:.2f}" text-anchor="middle" fill="{esc(foreground)}" font-size="32" font-family="sans-serif" font-weight="700">{esc(year)}</text>',
                f'<text x="{x:.2f}" y="{text_y + (40 if up else 42):.2f}" text-anchor="middle" fill="{esc(foreground)}" font-size="24" font-family="sans-serif">{esc(desc)}</text>',
            ]
        )
    return svg_shell(width, height, "".join(body), background)


def _embed_image(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def map_overlay(
    title: str,
    points: list[dict[str, Any]],
    *,
    width: int = 1920,
    height: int = 1080,
    background_image: Path | None = None,
    background: str = "#101114",
    foreground: str = "#F5F5F5",
    accent: str = "#FF6B6B",
) -> str:
    if not points:
        raise GraphicsError("map overlay requires at least one point")
    body = [
        f'<text x="120" y="110" fill="{esc(foreground)}" font-size="64" font-family="sans-serif" font-weight="700">{esc(title)}</text>'
    ]
    map_x, map_y, map_w, map_h = 110, 170, width - 220, height - 270
    if background_image is not None:
        if not background_image.exists():
            raise GraphicsError(f"Map background not found: {background_image}")
        body.append(
            f'<image href="{_embed_image(background_image)}" x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}" preserveAspectRatio="xMidYMid slice"/>'
        )
    else:
        body.append(
            f'<rect x="{map_x}" y="{map_y}" width="{map_w}" height="{map_h}" rx="30" fill="#181B20" stroke="{esc(foreground)}" stroke-opacity=".25" stroke-width="3"/>'
        )
        for lon in (-120, -60, 0, 60, 120):
            x = map_x + (lon + 180) / 360 * map_w
            body.append(f'<line x1="{x:.2f}" y1="{map_y}" x2="{x:.2f}" y2="{map_y+map_h}" stroke="{esc(foreground)}" stroke-opacity=".12" stroke-width="2"/>')
        for lat in (-60, -30, 0, 30, 60):
            y = map_y + (90 - lat) / 180 * map_h
            body.append(f'<line x1="{map_x}" y1="{y:.2f}" x2="{map_x+map_w}" y2="{y:.2f}" stroke="{esc(foreground)}" stroke-opacity=".12" stroke-width="2"/>')
    for point in points:
        if "x" in point and "y" in point:
            px = map_x + float(point["x"]) * map_w
            py = map_y + float(point["y"]) * map_h
        else:
            lat = max(-90.0, min(90.0, float(point["lat"])))
            lon = max(-180.0, min(180.0, float(point["lon"])))
            px = map_x + (lon + 180.0) / 360.0 * map_w
            py = map_y + (90.0 - lat) / 180.0 * map_h
        label = point.get("label", "")
        body.extend(
            [
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="18" fill="{esc(accent)}" stroke="#FFFFFF" stroke-width="5"/>',
                f'<text x="{px + 28:.2f}" y="{py - 18:.2f}" fill="{esc(foreground)}" font-size="30" font-family="sans-serif" font-weight="700">{esc(label)}</text>',
            ]
        )
    return svg_shell(width, height, "".join(body), background)


def insertion_steps(asset: Path, *, prefix: str, at: float, duration: float, track_name: str = "Documentary Graphics") -> list[dict[str, Any]]:
    return [
        {
            "id": f"{prefix}-track",
            "tool": "kdenlive_add_track",
            "arguments": {"audio": False, "name": track_name},
        },
        {
            "id": f"{prefix}-import",
            "tool": "kdenlive_import_media",
            "arguments": {"path": str(asset.resolve())},
        },
        {
            "id": f"{prefix}-insert",
            "tool": "kdenlive_insert_bin_clip",
            "arguments": {
                "bin_id": {"$ref": f"{prefix}-import.result.bin_id"},
                "track_id": {"$ref": f"{prefix}-track.result.track_id"},
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
                        "track_id": {"$ref": f"{prefix}-track.result.track_id"},
                        "position_seconds": at + min(0.05, max(0.001, duration / 10.0)),
                    }
                },
                "duration_seconds": duration,
                "edge": "right",
                "allow_single_resize": True,
            },
        },
    ]


def compile_graphics(config: dict[str, Any], output_dir: Path) -> tuple[list[Path], dict[str, Any]]:
    operations = config.get("graphics")
    if not isinstance(operations, list) or not operations:
        raise GraphicsError("Config requires a non-empty graphics array")
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    plan: dict[str, Any] = {
        "format": "update-p5-ai-edit",
        "version": 1,
        "metadata": {
            "title": str(config.get("title", "Documentary graphics")),
            "generated_by": "Update P5 Documentary Graphics",
        },
        "safety": {"checkpoint": True, "checkpoint_label": "before-documentary-graphics"},
        "steps": [],
    }
    for index, item in enumerate(operations, 1):
        if not isinstance(item, dict):
            raise GraphicsError(f"graphics[{index-1}] must be an object")
        kind = str(item.get("type", ""))
        title = str(item.get("title", ""))
        width = int(item.get("width", 1920))
        height = int(item.get("height", 1080))
        background = str(item.get("background", "#101114"))
        foreground = str(item.get("foreground", "#F5F5F5"))
        accent = str(item.get("accent", "#68A7FF"))
        if kind == "bar_chart":
            svg = bar_chart(title, item.get("items", []), width=width, height=height, background=background, foreground=foreground, accent=accent)
        elif kind == "line_chart":
            svg = line_chart(title, item.get("points", []), width=width, height=height, background=background, foreground=foreground, accent=accent)
        elif kind == "timeline":
            svg = timeline_graphic(title, item.get("events", []), width=width, height=height, background=background, foreground=foreground, accent=accent)
        elif kind == "map":
            bg = item.get("background_image")
            bg_path = None if not bg else Path(str(bg))
            svg = map_overlay(title, item.get("points", []), width=width, height=height, background_image=bg_path, background=background, foreground=foreground, accent=accent)
        else:
            raise GraphicsError(f"Unsupported graphic type: {kind!r}")
        asset = output_dir / f"graphic-{index:03d}-{kind}.svg"
        asset.write_text(svg, encoding="utf-8")
        assets.append(asset)
        at = float(item.get("at", 0.0))
        duration = float(item.get("duration", 5.0))
        if duration <= 0:
            raise GraphicsError("graphic duration must be positive")
        plan["steps"].extend(insertion_steps(asset, prefix=f"graphic-{index:03d}", at=at, duration=duration))
    plan["steps"].append({"id": "save-after-documentary-graphics", "tool": "kdenlive_save_project", "arguments": {}})
    plan["metadata"]["graphic_count"] = len(assets)
    return assets, plan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate documentary SVG graphics and native insertion plan")
    p.add_argument("config", type=Path)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--plan-output", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GraphicsError(f"Invalid graphics config JSON: {exc}") from exc
        if not isinstance(config, dict):
            raise GraphicsError("Graphics config root must be an object")
        assets, plan = compile_graphics(config, args.output_dir)
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(assets)} SVG assets and {args.plan_output}")
        return 0
    except (GraphicsError, OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

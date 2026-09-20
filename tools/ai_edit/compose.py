#!/usr/bin/env python3
"""Compose multiple Update P5 AI Edit JSON files into one deterministic plan."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
_RUNNER_SPEC = importlib.util.spec_from_file_location("update_p5_ai_edit_runner", HERE / "update_p5_ai_edit.py")
_runner = importlib.util.module_from_spec(_RUNNER_SPEC)
assert _RUNNER_SPEC.loader
_RUNNER_SPEC.loader.exec_module(_runner)

FORMAT = _runner.FORMAT
VERSION = _runner.VERSION


class ComposeError(RuntimeError):
    pass


def load_plan(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ComposeError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ComposeError(f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(doc, dict):
        raise ComposeError(f"{path}: plan must be one JSON object")
    errors = _runner.validate_plan(doc)
    if errors:
        raise ComposeError(f"{path}: invalid AI Edit plan: " + "; ".join(errors))
    return doc


def slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_").lower()
    return cleaned or fallback


def rewrite_refs(value: Any, id_map: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [rewrite_refs(item, id_map) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"$ref"} and isinstance(value["$ref"], str):
        ref = value["$ref"]
        step_id, dot, rest = ref.partition(".")
        if step_id in id_map:
            return {"$ref": id_map[step_id] + (("." + rest) if dot else "")}
        return dict(value)
    return {key: rewrite_refs(item, id_map) for key, item in value.items()}


def compose_plans(
    sources: list[tuple[Path, dict[str, Any]]],
    *,
    title: str = "Composed AI edit",
    collapse_saves: bool = True,
) -> dict[str, Any]:
    if not sources:
        raise ComposeError("At least one input plan is required")

    variables: dict[str, Any] = {}
    output_steps: list[dict[str, Any]] = []
    source_meta: list[dict[str, Any]] = []
    saw_save = False
    checkpoint = False

    for index, (path, doc) in enumerate(sources, 1):
        prefix = slug(path.stem, f"plan-{index}")
        source_meta.append(
            {
                "file": str(path),
                "title": doc.get("metadata", {}).get("title") if isinstance(doc.get("metadata"), dict) else None,
            }
        )

        for key, value in doc.get("variables", {}).items():
            if key in variables and variables[key] != value:
                raise ComposeError(
                    f"Variable {key!r} has conflicting values in the input plans: "
                    f"{variables[key]!r} vs {value!r}"
                )
            variables[key] = value

        safety = doc.get("safety", {})
        if isinstance(safety, dict) and safety.get("checkpoint", True):
            checkpoint = True

        enabled_steps = [
            step for step in doc["steps"]
            if isinstance(step, dict) and step.get("enabled", True)
        ]
        id_map = {
            str(step["id"]): f"{prefix}-{step['id']}"
            for step in enabled_steps
        }

        for step in enabled_steps:
            tool = str(step["tool"])
            if collapse_saves and tool == "kdenlive_save_project":
                saw_save = True
                continue
            rewritten = dict(step)
            rewritten["id"] = id_map[str(step["id"])]
            rewritten["arguments"] = rewrite_refs(step.get("arguments", {}), id_map)
            output_steps.append(rewritten)

    if collapse_saves and saw_save:
        final_id = "save-final"
        used = {str(step["id"]) for step in output_steps}
        suffix = 2
        while final_id in used:
            final_id = f"save-final-{suffix}"
            suffix += 1
        output_steps.append({"id": final_id, "tool": "kdenlive_save_project", "arguments": {}})

    result: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "metadata": {
            "title": title,
            "generated_by": "Update P5 AI Edit Composer",
            "source_plans": source_meta,
        },
        "safety": {
            "checkpoint": checkpoint,
            "checkpoint_label": "before-composed-ai-edit",
        },
        "steps": output_steps,
    }
    if variables:
        result["variables"] = variables

    errors = _runner.validate_plan(result)
    if errors:
        raise ComposeError("Composed plan failed validation: " + "; ".join(errors))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge multiple Update P5 AI Edit JSON files into one plan"
    )
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--title", default="Composed AI edit")
    parser.add_argument(
        "--keep-intermediate-saves",
        action="store_true",
        help="Keep every kdenlive_save_project step instead of collapsing them into one final save",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sources = [(path, load_plan(path)) for path in args.inputs]
        result = compose_plans(
            sources,
            title=args.title,
            collapse_saves=not args.keep_intermediate_saves,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.output} ({len(result['steps'])} steps from {len(sources)} plans)")
        return 0
    except (ComposeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Creator Pipeline orchestration for Update P5 Edit Aja.

Runs repo-local feature scripts in sequence, tracks named artifacts, and can
compose all produced Phase 6 AI Edit JSON plans into one final plan.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


class PipelineError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = ROOT / "tools" / "ai_edit" / "compose.py"
TOKEN_RE = re.compile(r"\{\{([^}]+)\}\}")


def _load_compose():
    spec = importlib.util.spec_from_file_location("update_p5_compose", COMPOSE_PATH)
    if spec is None or spec.loader is None:
        raise PipelineError(f"Could not load AI Edit composer: {COMPOSE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid pipeline JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError("Pipeline root must be an object")
    if not isinstance(data.get("stages"), list):
        raise PipelineError("Pipeline requires a stages array")
    return data


def resolve_string(value: str, context: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise PipelineError("Unknown pipeline token: {{" + key + "}}")
        return context[key]
    return TOKEN_RE.sub(repl, value)


def initial_context(config: dict[str, Any], workdir: Path) -> dict[str, str]:
    ctx = {
        "root": str(ROOT),
        "workdir": str(workdir.resolve()),
        "python": sys.executable,
    }
    variables = config.get("variables", {})
    if not isinstance(variables, dict):
        raise PipelineError("variables must be an object")
    for key, value in variables.items():
        ctx[str(key)] = resolve_string(str(value), ctx)
    return ctx


def stage_command(stage: dict[str, Any], context: dict[str, str]) -> list[str]:
    args = stage.get("args", [])
    if not isinstance(args, list):
        raise PipelineError(f"Stage {stage.get('id')}: args must be an array")
    resolved_args = [resolve_string(str(x), context) for x in args]
    if stage.get("script"):
        script_path = Path(resolve_string(str(stage["script"]), context))
        if not script_path.is_absolute():
            script_path = ROOT / script_path
        return [sys.executable, str(script_path)] + resolved_args
    if stage.get("command"):
        return [resolve_string(str(stage["command"]), context)] + resolved_args
    raise PipelineError(f"Stage {stage.get('id')}: provide script or command")


def register_outputs(
    stage: dict[str, Any],
    context: dict[str, str],
    *,
    require_exists: bool,
) -> dict[str, str]:
    stage_id = str(stage["id"])
    outputs = stage.get("outputs", {})
    if not isinstance(outputs, dict):
        raise PipelineError(f"Stage {stage_id}: outputs must be an object")
    registered = {}
    for name, raw in outputs.items():
        value = resolve_string(str(raw), context)
        path = Path(value)
        if not path.is_absolute():
            path = Path(context["workdir"]) / path
        path = path.resolve()
        if require_exists and not path.exists():
            raise PipelineError(f"Stage {stage_id}: expected output missing: {path}")
        key = f"{stage_id}.{name}"
        context[key] = str(path)
        registered[str(name)] = str(path)
    return registered


def execute_pipeline(
    config: dict[str, Any],
    *,
    workdir: Path,
    dry_run: bool = False,
    stop_on_error: bool = True,
) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    context = initial_context(config, workdir)
    report_stages = []
    plan_paths: list[Path] = []
    ids: set[str] = set()

    for index, raw_stage in enumerate(config["stages"], 1):
        if not isinstance(raw_stage, dict):
            raise PipelineError(f"stages[{index-1}] must be an object")
        stage = dict(raw_stage)
        stage_id = str(stage.get("id", f"stage-{index:03d}"))
        if stage_id in ids:
            raise PipelineError(f"Duplicate stage id: {stage_id}")
        ids.add(stage_id)
        stage["id"] = stage_id
        optional = bool(stage.get("optional", False))

        if not bool(stage.get("enabled", True)):
            report_stages.append({"id": stage_id, "status": "disabled"})
            continue

        cmd = stage_command(stage, context)
        entry: dict[str, Any] = {"id": stage_id, "command": cmd, "optional": optional}

        if dry_run:
            outputs = register_outputs(stage, context, require_exists=False)
            entry.update({"status": "planned", "outputs": outputs})
            report_stages.append(entry)
            plan_ref = stage.get("plan_output")
            if plan_ref:
                plan_paths.append(Path(resolve_string(str(plan_ref), context)))
            continue

        env = os.environ.copy()
        extra_env = stage.get("env", {})
        if not isinstance(extra_env, dict):
            raise PipelineError(f"Stage {stage_id}: env must be an object")
        for key, value in extra_env.items():
            env[str(key)] = resolve_string(str(value), context)

        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        entry["returncode"] = proc.returncode
        entry["stdout"] = proc.stdout[-12000:]
        entry["stderr"] = proc.stderr[-12000:]

        if proc.returncode != 0:
            entry["status"] = "optional_failed" if optional else "failed"
            report_stages.append(entry)
            if not optional and stop_on_error:
                return {
                    "format": "update-p5-creator-pipeline-report",
                    "version": 1,
                    "success": False,
                    "workdir": str(workdir.resolve()),
                    "stages": report_stages,
                    "artifacts": dict(context),
                }
            continue

        outputs = register_outputs(stage, context, require_exists=True)
        entry.update({"status": "success", "outputs": outputs})
        report_stages.append(entry)

        plan_ref = stage.get("plan_output")
        if plan_ref:
            plan_path = Path(resolve_string(str(plan_ref), context))
            if not plan_path.is_absolute():
                plan_path = workdir / plan_path
            plan_path = plan_path.resolve()
            if not plan_path.exists():
                raise PipelineError(f"Stage {stage_id}: declared plan_output missing: {plan_path}")
            plan_paths.append(plan_path)

    final_plan_path = None
    compose_cfg = config.get("compose", {})
    if compose_cfg is not False and plan_paths and not dry_run:
        if not isinstance(compose_cfg, dict):
            compose_cfg = {}
        compose = _load_compose()
        sources = [(p, compose.load_plan(p)) for p in plan_paths]
        final = compose.compose_plans(
            sources,
            title=str(compose_cfg.get("title", config.get("title", "Creator Pipeline Edit"))),
            collapse_saves=bool(compose_cfg.get("collapse_saves", True)),
        )
        final_raw = resolve_string(str(compose_cfg.get("output", "final.edit.json")), context)
        final_plan_path = Path(final_raw)
        if not final_plan_path.is_absolute():
            final_plan_path = workdir / final_plan_path
        final_plan_path = final_plan_path.resolve()
        final_plan_path.parent.mkdir(parents=True, exist_ok=True)
        final_plan_path.write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        context["final_plan"] = str(final_plan_path)

    success = all(x["status"] in {"success", "planned", "disabled", "optional_failed"} for x in report_stages)
    return {
        "format": "update-p5-creator-pipeline-report",
        "version": 1,
        "success": success,
        "title": config.get("title"),
        "workdir": str(workdir.resolve()),
        "stages": report_stages,
        "plan_inputs": [str(x) for x in plan_paths],
        "final_plan": str(final_plan_path) if final_plan_path else None,
        "artifacts": dict(context),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run a multi-stage Update P5 creator workflow")
    p.add_argument("pipeline", type=Path)
    p.add_argument("--workdir", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--continue-on-error", action="store_true")
    p.add_argument("--report", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.pipeline)
        workdir = args.workdir or Path(cfg.get("workdir", "./update-p5-work"))
        report = execute_pipeline(
            cfg,
            workdir=workdir,
            dry_run=args.dry_run,
            stop_on_error=not args.continue_on_error,
        )
        text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text, encoding="utf-8")
            print(f"Wrote {args.report}")
        else:
            print(text, end="")
        return 0 if report["success"] else 1
    except (PipelineError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

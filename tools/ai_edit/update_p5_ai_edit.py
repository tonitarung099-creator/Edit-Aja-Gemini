#!/usr/bin/env python3
"""Update P5 Edit Aja AI Edit JSON runner.

Executes a deterministic JSON edit plan against the Phase 5 localhost REST
bridge. It does not use an LLM and does not replace the built-in AI Agent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

FORMAT = "update-p5-ai-edit"
VERSION = 1
DISCOVERY_NAME = "kdenlive-open-agent.json"


class PlanError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise PlanError("AI edit file must contain one JSON object")
    return data


def _validate_special(value: Any, where: str, errors: list[str]) -> None:
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_special(item, f"{where}[{i}]", errors)
        return
    if not isinstance(value, dict):
        return
    special = [k for k in ("$ref", "$var", "$clip_at", "$track") if k in value]
    if len(special) > 1:
        errors.append(f"{where}: only one special resolver is allowed per object")
    if "$ref" in value and (len(value) != 1 or not isinstance(value["$ref"], str)):
        errors.append(f"{where}: $ref must be the only key and contain a string")
    if "$var" in value and (len(value) != 1 or not isinstance(value["$var"], str)):
        errors.append(f"{where}: $var must be the only key and contain a string")
    if "$clip_at" in value:
        spec = value["$clip_at"]
        if len(value) != 1 or not isinstance(spec, dict):
            errors.append(f"{where}: $clip_at must be the only key and contain an object")
        elif not any(k in spec for k in ("position_frame", "position_seconds")):
            errors.append(f"{where}: $clip_at requires position_frame or position_seconds")
    if "$track" in value:
        spec = value["$track"]
        if len(value) != 1 or not isinstance(spec, dict):
            errors.append(f"{where}: $track must be the only key and contain an object")
    if not special:
        for key, item in value.items():
            _validate_special(item, f"{where}.{key}", errors)


def validate_plan(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("format") != FORMAT:
        errors.append(f"format must be {FORMAT!r}")
    if doc.get("version") != VERSION:
        errors.append(f"version must be {VERSION}")
    variables = doc.get("variables", {})
    if not isinstance(variables, dict):
        errors.append("variables must be an object")
    safety = doc.get("safety", {})
    if not isinstance(safety, dict):
        errors.append("safety must be an object")
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty array")
        return errors
    seen: set[str] = set()
    for i, step in enumerate(steps):
        where = f"steps[{i}]"
        if not isinstance(step, dict):
            errors.append(f"{where} must be an object")
            continue
        step_id = step.get("id")
        tool = step.get("tool")
        arguments = step.get("arguments", {})
        if not isinstance(step_id, str) or not step_id.strip():
            errors.append(f"{where}.id must be a non-empty string")
        elif step_id in seen:
            errors.append(f"{where}.id duplicates {step_id!r}")
        else:
            seen.add(step_id)
        if not isinstance(tool, str) or not tool.startswith("kdenlive_"):
            errors.append(f"{where}.tool must be a kdenlive_* tool name")
        if not isinstance(arguments, dict):
            errors.append(f"{where}.arguments must be an object")
        else:
            _validate_special(arguments, f"{where}.arguments", errors)
        if "enabled" in step and not isinstance(step["enabled"], bool):
            errors.append(f"{where}.enabled must be boolean")
    return errors


class RestClient:
    def __init__(self, discovery_path: Path | None = None, timeout: int = 60):
        self.discovery_path = discovery_path or Path(tempfile.gettempdir()) / DISCOVERY_NAME
        self.timeout = timeout
        self._info: dict[str, Any] | None = None

    def discovery(self) -> dict[str, Any]:
        if self._info is None:
            if not self.discovery_path.exists():
                raise PlanError(
                    f"Discovery file not found: {self.discovery_path}. "
                    "Start Update P5 Edit Aja and open the AI Agent panel first."
                )
            self._info = _load_json(self.discovery_path)
            if not self._info.get("rest_base_url") or not self._info.get("token"):
                raise PlanError("Discovery file is missing rest_base_url or token")
        return self._info

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        info = self.discovery()
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{str(info['rest_base_url']).rstrip('/')}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {info['token']}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PlanError(f"REST HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise PlanError(f"Could not reach Update P5 Edit Aja REST bridge: {exc.reason}") from exc
        if not isinstance(parsed, dict):
            raise PlanError("REST bridge returned a non-object JSON response")
        return parsed

    def list_tools(self) -> list[dict[str, Any]]:
        response = self.request("GET", "/tools")
        tools = response.get("tools", [])
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("POST", "/tools/call", {"name": name, "arguments": arguments or {}})


def _json_path(root: Any, path: str) -> Any:
    current = root
    for part in path.split(".") if path else []:
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise PlanError(f"Invalid list path component {part!r} in reference {path!r}") from exc
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise PlanError(f"Reference path not found: {path!r}")
    return current


def _inner_result(response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result")
    return result if isinstance(result, dict) else {}


def _timeline_state(client: RestClient) -> dict[str, Any]:
    response = client.call_tool("kdenlive_get_timeline_state", {"include_items": True})
    result = _inner_result(response)
    if not response.get("ok") or not result.get("ok"):
        raise PlanError(f"Could not inspect timeline: {response}")
    return result


def _resolve_track(spec: dict[str, Any], client: RestClient, context: dict[str, Any], variables: dict[str, Any], base_dir: Path) -> int:
    state = _timeline_state(client)
    tracks = [t for t in state.get("tracks", []) if isinstance(t, dict)]
    if "id" in spec:
        return int(_resolve(spec["id"], client, context, variables, base_dir))
    if "audio" in spec:
        tracks = [t for t in tracks if bool(t.get("audio")) == bool(spec["audio"])]
    if "tag" in spec:
        tag = str(spec["tag"])
        tracks = [t for t in tracks if str(t.get("tag", "")) == tag]
    if "position" in spec:
        tracks = [t for t in tracks if int(t.get("position", -1)) == int(spec["position"])]
    index = int(spec.get("index", 0))
    if index < 0 or index >= len(tracks):
        raise PlanError(f"$track selector matched {len(tracks)} tracks; index {index} is invalid")
    return int(tracks[index]["id"])


def _resolve_clip_at(spec: dict[str, Any], client: RestClient, context: dict[str, Any], variables: dict[str, Any], base_dir: Path) -> int:
    state = _timeline_state(client)
    fps = float(state.get("fps") or 0)
    if "position_frame" in spec:
        frame = int(_resolve(spec["position_frame"], client, context, variables, base_dir))
    else:
        if fps <= 0:
            raise PlanError("Timeline fps is unavailable for $clip_at seconds conversion")
        seconds = float(_resolve(spec.get("position_seconds", 0), client, context, variables, base_dir))
        frame = round(seconds * fps)
    track_id = None
    if "track_id" in spec:
        track_id = int(_resolve(spec["track_id"], client, context, variables, base_dir))
    elif "track" in spec:
        track_spec = spec["track"]
        if not isinstance(track_spec, dict):
            raise PlanError("$clip_at.track must be an object")
        track_id = _resolve_track(track_spec, client, context, variables, base_dir)
    candidates = []
    for item in state.get("items", []):
        if not isinstance(item, dict) or item.get("kind") != "clip":
            continue
        if track_id is not None and int(item.get("track_id", -1)) != track_id:
            continue
        start = int(item.get("position_frame", -1))
        end = int(item.get("end_frame", -1))
        if start <= frame < end:
            candidates.append(item)
    if len(candidates) != 1:
        raise PlanError(f"$clip_at expected exactly one clip at frame {frame}, found {len(candidates)}")
    return int(candidates[0]["id"])


def _resolve(value: Any, client: RestClient | None, context: dict[str, Any], variables: dict[str, Any], base_dir: Path) -> Any:
    if isinstance(value, list):
        return [_resolve(v, client, context, variables, base_dir) for v in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"$var"}:
        name = str(value["$var"])
        if name not in variables:
            raise PlanError(f"Unknown variable: {name}")
        return variables[name]
    if set(value) == {"$ref"}:
        ref = str(value["$ref"])
        step_id, dot, rest = ref.partition(".")
        if step_id not in context:
            raise PlanError(f"Reference uses step {step_id!r} before it has run")
        return _json_path(context[step_id], rest if dot else "")
    if set(value) == {"$track"}:
        if client is None:
            return value
        return _resolve_track(value["$track"], client, context, variables, base_dir)
    if set(value) == {"$clip_at"}:
        if client is None:
            return value
        return _resolve_clip_at(value["$clip_at"], client, context, variables, base_dir)
    return {k: _resolve(v, client, context, variables, base_dir) for k, v in value.items()}


def _normalize_paths(tool: str, arguments: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    result = dict(arguments)
    keys: set[str] = set()
    if tool in {"kdenlive_import_media", "kdenlive_import_subtitles", "kdenlive_export_subtitles", "kdenlive_export_frame"}:
        keys.add("path")
    if tool == "kdenlive_save_project":
        keys.add("path")
    if tool == "kdenlive_render":
        keys.add("output_path")
    if tool in {"kdenlive_detect_silence", "kdenlive_transcribe_media"} and result.get("path"):
        keys.add("path")
    for key in keys:
        raw = result.get(key)
        if isinstance(raw, str) and raw and not os.path.isabs(raw):
            result[key] = str((base_dir / raw).resolve())
    return result


def _variables(doc: dict[str, Any], overrides: list[str]) -> dict[str, Any]:
    values = dict(doc.get("variables", {}))
    for item in overrides:
        if "=" not in item:
            raise PlanError(f"--var requires NAME=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        values[key] = value
    return values


def _catalog_map(client: RestClient) -> dict[str, dict[str, Any]]:
    return {str(t.get("name")): t for t in client.list_tools() if isinstance(t, dict) and t.get("name")}


def apply_plan(path: Path, doc: dict[str, Any], client: RestClient, variables: dict[str, Any], yes: bool, checkpoint: bool, continue_on_error: bool) -> dict[str, Any]:
    catalog = _catalog_map(client)
    missing = sorted({str(s["tool"]) for s in doc["steps"] if s.get("enabled", True) and str(s["tool"]) not in catalog})
    if missing:
        raise PlanError("Running editor does not expose required tools: " + ", ".join(missing))
    enabled = [s for s in doc["steps"] if s.get("enabled", True)]
    if not yes:
        print(f"Plan has {len(enabled)} enabled steps. Type APPLY to execute against the current timeline: ", end="", flush=True)
        if input().strip() != "APPLY":
            raise PlanError("Cancelled")
    context: dict[str, Any] = {}
    report: dict[str, Any] = {"format": FORMAT, "source": str(path), "steps": []}
    safety = doc.get("safety", {})
    if checkpoint and safety.get("checkpoint", True) and "kdenlive_checkpoint_project" in catalog:
        label = str(safety.get("checkpoint_label", "ai-edit-json"))
        checkpoint_response = client.call_tool("kdenlive_checkpoint_project", {"label": label})
        report["checkpoint"] = checkpoint_response
        inner = _inner_result(checkpoint_response)
        if not checkpoint_response.get("ok") or (inner and inner.get("ok") is False):
            raise PlanError(f"Checkpoint failed: {checkpoint_response}")
    for step in enabled:
        step_id = str(step["id"])
        tool = str(step["tool"])
        try:
            args = _resolve(step.get("arguments", {}), client, context, variables, path.parent)
            args = _normalize_paths(tool, args, path.parent)
            response = client.call_tool(tool, args)
            context[step_id] = response
            entry = {"id": step_id, "tool": tool, "arguments": args, "response": response}
            report["steps"].append(entry)
            inner = _inner_result(response)
            failed = not response.get("ok") or (inner and inner.get("ok") is False)
            if failed and not continue_on_error:
                raise PlanError(f"Step {step_id!r} failed: {response}")
        except Exception as exc:
            if not any(r.get("id") == step_id for r in report["steps"]):
                report["steps"].append({"id": step_id, "tool": tool, "error": str(exc)})
            if not continue_on_error:
                raise
    report["ok"] = all("error" not in s and not (_inner_result(s.get("response", {})).get("ok") is False) for s in report["steps"])
    return report


def static_plan(path: Path, doc: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    steps = []
    for step in doc["steps"]:
        if not step.get("enabled", True):
            continue
        try:
            args = _resolve(step.get("arguments", {}), None, context, variables, path.parent)
            args = _normalize_paths(str(step["tool"]), args, path.parent)
        except PlanError:
            args = step.get("arguments", {})
        steps.append({"id": step["id"], "tool": step["tool"], "arguments": args})
    return {"format": FORMAT, "version": VERSION, "steps": steps}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or execute Update P5 AI Edit JSON plans")
    parser.add_argument("--discovery", type=Path, help="Override kdenlive-open-agent.json path")
    parser.add_argument("--timeout", type=int, default=60, help="REST timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate", help="Validate a JSON plan without connecting to the editor")
    p_validate.add_argument("plan", type=Path)
    p_plan = sub.add_parser("plan", help="Print a normalized static execution plan")
    p_plan.add_argument("plan", type=Path)
    p_plan.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    sub.add_parser("catalog", help="List tools exposed by the running editor")
    p_apply = sub.add_parser("apply", help="Apply a JSON plan to the running editor")
    p_apply.add_argument("plan", type=Path)
    p_apply.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    p_apply.add_argument("--yes", action="store_true", help="Skip the APPLY confirmation prompt")
    p_apply.add_argument("--no-checkpoint", action="store_true", help="Do not create the automatic safety checkpoint")
    p_apply.add_argument("--continue-on-error", action="store_true")
    p_apply.add_argument("--report", type=Path, help="Write full execution report JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            client = RestClient(args.discovery, args.timeout)
            print(json.dumps(client.list_tools(), indent=2, ensure_ascii=False))
            return 0
        doc = _load_json(args.plan)
        errors = validate_plan(doc)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 2
        if args.command == "validate":
            print(f"OK: {args.plan} ({len(doc['steps'])} steps)")
            return 0
        vars_ = _variables(doc, args.var)
        if args.command == "plan":
            print(json.dumps(static_plan(args.plan, doc, vars_), indent=2, ensure_ascii=False))
            return 0
        client = RestClient(args.discovery, args.timeout)
        report = apply_plan(
            args.plan,
            doc,
            client,
            vars_,
            yes=args.yes,
            checkpoint=not args.no_checkpoint,
            continue_on_error=args.continue_on_error,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.report:
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return 0 if report.get("ok") else 3
    except (PlanError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

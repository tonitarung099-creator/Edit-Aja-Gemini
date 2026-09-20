#!/usr/bin/env python3
"""Capability registry / dependency doctor for Update P5 Edit Aja."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any


class CapabilityError(RuntimeError):
    pass


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = ROOT / "capabilities" / "registry.json"


def load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CapabilityError(f"Registry not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CapabilityError(f"Invalid registry JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), list):
        raise CapabilityError("Invalid capability registry")
    return data


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def inspect_capability(capability: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    executables = [str(x) for x in capability.get("executables", [])]
    modules = [str(x) for x in capability.get("python_modules", [])]
    script = root / str(capability.get("script", ""))
    exe_status = {name: shutil.which(name) for name in executables}
    module_status = {name: module_available(name) for name in modules}
    missing = [f"exe:{name}" for name, path in exe_status.items() if not path]
    missing += [f"py:{name}" for name, available in module_status.items() if not available]
    if not script.exists():
        missing.append(f"script:{capability.get('script')}")
    return {
        "id": capability.get("id"),
        "name": capability.get("name"),
        "category": capability.get("category"),
        "optional": bool(capability.get("optional", False)),
        "available": not missing,
        "script": str(script),
        "executables": exe_status,
        "python_modules": module_status,
        "missing": missing,
    }


def inspect_all(registry: dict[str, Any], root: Path = ROOT) -> list[dict[str, Any]]:
    return [
        inspect_capability(item, root)
        for item in registry["capabilities"]
        if isinstance(item, dict)
    ]


def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    available = [x for x in items if x["available"]]
    missing_required = [x for x in items if not x["available"] and not x["optional"]]
    missing_optional = [x for x in items if not x["available"] and x["optional"]]
    return {
        "total": len(items),
        "available": len(available),
        "missing_required": len(missing_required),
        "missing_optional": len(missing_optional),
        "ready": not missing_required,
    }


def print_human(items: list[dict[str, Any]]) -> None:
    for item in items:
        status = "READY" if item["available"] else ("OPTIONAL" if item["optional"] else "MISSING")
        print(f"[{status:8}] {item['id']}: {item['name']}")
        if item["missing"]:
            print("           missing: " + ", ".join(item["missing"]))
    s = summary(items)
    print()
    print(
        f"Capabilities: {s['available']}/{s['total']} available; "
        f"{s['missing_required']} required missing; {s['missing_optional']} optional missing."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect Update P5 optional feature dependencies")
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--json", action="store_true")
    p.add_argument("--category")
    p.add_argument("--id")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_registry(args.registry)
        items = inspect_all(registry)
        if args.category:
            items = [x for x in items if x["category"] == args.category]
        if args.id:
            items = [x for x in items if x["id"] == args.id]
            if not items:
                raise CapabilityError(f"Unknown capability id: {args.id}")
        if args.json:
            print(json.dumps({"summary": summary(items), "capabilities": items}, indent=2, ensure_ascii=False))
        else:
            print_human(items)
        return 0 if summary(items)["missing_required"] == 0 else 3
    except (CapabilityError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

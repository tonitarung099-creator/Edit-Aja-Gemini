import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (ROOT / "build" / "build-manifest.json").read_text(encoding="utf-8")
)


def patch_entry(name: str) -> dict:
    for entry in MANIFEST["patches"]:
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def apply_entry(name: str) -> dict:
    for entry in MANIFEST["apply_chain"]:
        if entry["name"] == name:
            return entry
    raise KeyError(name)


def payload_entry(source: str) -> dict:
    for entry in MANIFEST.get("blueprint_payloads", []):
        if entry["source"] == source:
            return entry
    raise KeyError(source)


def read_windows_script(name: str) -> str:
    return (ROOT / "scripts" / "windows" / name).read_text(encoding="utf-8")

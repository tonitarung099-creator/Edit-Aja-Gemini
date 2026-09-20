#!/usr/bin/env python3
"""Prepare generated Craft patch inputs from the pinned build manifest."""

import argparse
import base64
import bz2
import hashlib
import json
import shutil
from pathlib import Path


def load_manifest(root: Path, manifest_path: Path) -> dict:
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    return json.loads(path.read_text(encoding="utf-8"))


def prepare(root: Path, manifest_path: Path) -> None:
    manifest = load_manifest(root, manifest_path)

    for patch in manifest["patches"]:
        encoded = "".join((root / source).read_text(encoding="utf-8") for source in patch["sources"])
        data = bz2.decompress(base64.b64decode(encoded))
        digest = hashlib.sha256(data).hexdigest()
        print(f'{patch["name"]} SHA-256: {digest}')
        if digest != patch["sha256"]:
            raise SystemExit(
                f'{patch["name"]} checksum mismatch: expected {patch["sha256"]}, got {digest}'
            )
        output = root / patch["output"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)

    for payload in manifest.get("blueprint_payloads", []):
        source = root / payload["source"]
        destination = root / payload["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        print(f"Copied blueprint payload: {payload['source']} -> {payload['destination']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=Path("build/build-manifest.json"))
    args = parser.parse_args()
    prepare(args.root.resolve(), args.manifest)

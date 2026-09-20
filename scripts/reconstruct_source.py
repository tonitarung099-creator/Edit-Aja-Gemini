#!/usr/bin/env python3
"""Reconstruct and verify the pinned P5 source tree on any supported CI host."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from apply_branding import apply as apply_branding
from prepare_build_inputs import prepare as prepare_build_inputs
from verify_p5_source import verify as verify_p5_source


def run(*args: str, cwd: Path | None = None) -> None:
    display = " ".join(args)
    print(f"+ {display}")
    subprocess.run(args, cwd=cwd, check=True)


def load_manifest(root: Path, manifest_path: Path) -> dict:
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    return json.loads(path.read_text(encoding="utf-8"))


def apply_patch(root: Path, source_root: Path, entry: dict) -> None:
    patch_path = (root / entry["path"]).resolve()
    strip = int(entry["strip"])

    if entry.get("check"):
        run(
            "git",
            "-C",
            str(source_root),
            "apply",
            "--check",
            f"-p{strip}",
            str(patch_path),
        )

    args = ["git", "-C", str(source_root), "apply"]
    if entry.get("ignore_space_change"):
        args.append("--ignore-space-change")
    args.extend((f"-p{strip}", str(patch_path)))

    print(f'Applying {entry["name"]}: {entry["path"]}')
    run(*args)


def write_source_archive(source_root: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.unlink(missing_ok=True)

    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for current_root, directories, filenames in os.walk(source_root):
            directories[:] = sorted(
                name for name in directories if name != ".git"
            )
            current = Path(current_root)
            for filename in sorted(filenames):
                path = current / filename
                archive.write(path, path.relative_to(source_root))

    print(f"Verified corresponding source archive: {archive_path}")


def reconstruct(
    root: Path,
    manifest_path: Path,
    source_root: Path,
    archive_path: Path | None = None,
) -> None:
    root = root.resolve()
    source_root = source_root if source_root.is_absolute() else root / source_root
    source_root = source_root.resolve()

    manifest = load_manifest(root, manifest_path)
    prepare_build_inputs(root, manifest_path)

    if source_root.exists():
        shutil.rmtree(source_root)

    run("git", "init", str(source_root))
    run(
        "git",
        "-C",
        str(source_root),
        "remote",
        "add",
        "origin",
        manifest["upstream"]["repository"],
    )
    run(
        "git",
        "-C",
        str(source_root),
        "fetch",
        "--depth",
        "1",
        "origin",
        manifest["upstream"]["commit"],
    )
    run("git", "-C", str(source_root), "checkout", "--detach", "FETCH_HEAD")

    for entry in manifest["apply_chain"]:
        apply_patch(root, source_root, entry)

    film_context_dir = source_root / "data" / "scripts" / "filmcontext"
    film_context_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        root / "tools" / "film_context" / "film_context.py",
        film_context_dir / "film_context.py",
    )

    apply_branding(source_root, root / "branding")
    verify_p5_source(source_root)

    if archive_path is not None:
        archive_path = archive_path if archive_path.is_absolute() else root / archive_path
        write_source_archive(source_root, archive_path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("build/build-manifest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("corresponding-source"),
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="Optional .zip path for the verified corresponding source.",
    )
    args = parser.parse_args()

    reconstruct(
        args.root,
        args.manifest,
        args.output,
        args.archive,
    )


if __name__ == "__main__":
    main()

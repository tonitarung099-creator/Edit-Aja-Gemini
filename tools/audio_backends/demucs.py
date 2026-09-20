#!/usr/bin/env python3
"""Optional Demucs stem-separation backend for Update P5 Edit Aja.

Runs an external/current Python environment with python -m demucs, discovers
the generated stems, and can build a Phase 6 plan that imports them onto native
audio tracks while optionally muting the original timeline audio.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class DemucsError(RuntimeError):
    pass


KNOWN_STEMS = ("vocals", "no_vocals", "drums", "bass", "other")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise DemucsError(f"Could not execute {args[0]}: {exc}") from exc


def demucs_available(python_exe: str) -> bool:
    proc = _run([python_exe, "-c", "import demucs"])
    return proc.returncode == 0


def run_demucs(
    media: Path,
    out_dir: Path,
    *,
    python_exe: str,
    model: str | None = None,
    two_stems: str | None = None,
    device: str | None = None,
    jobs: int = 0,
) -> None:
    if not demucs_available(python_exe):
        raise DemucsError(
            "Demucs is optional and is not installed in the selected Python environment."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    args = [python_exe, "-m", "demucs", "-o", str(out_dir)]
    if model:
        args += ["-n", model]
    if two_stems:
        args += ["--two-stems", two_stems]
    if device:
        args += ["-d", device]
    if jobs > 0:
        args += ["-j", str(jobs)]
    args.append(str(media))
    proc = _run(args)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise DemucsError(detail or "Demucs separation failed")


def discover_stems(out_dir: Path, source: Path) -> dict[str, Path]:
    source_stem = source.stem
    candidates = []
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".wav", ".mp3", ".flac", ".ogg"}:
            continue
        if path.parent.name == source_stem:
            candidates.append(path)
    if not candidates:
        candidates = [
            p for p in out_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"}
        ]
    stems: dict[str, Path] = {}
    for path in candidates:
        stem_name = path.stem.lower()
        if stem_name in KNOWN_STEMS:
            stems[stem_name] = path.resolve()
        elif stem_name.startswith("no_"):
            stems[stem_name] = path.resolve()
    if not stems:
        raise DemucsError(f"No recognizable stem files found under {out_dir}")
    return stems


def stable_copy(stems: dict[str, Path], destination: Path, source: Path) -> dict[str, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    copied={}
    for name,path in stems.items():
        target=destination/f"{source.stem}-{name}{path.suffix.lower()}"
        shutil.copy2(path,target)
        copied[name]=target.resolve()
    return copied


def build_plan(
    stems: dict[str, Path],
    *,
    at: float = 0.0,
    original_audio_track_index: int = 0,
    mute_original: bool = True,
) -> dict[str, Any]:
    steps=[]
    for index,(name,path) in enumerate(sorted(stems.items()),1):
        prefix=f"stem-{index:02d}-{name}"
        steps += [
            {
                "id":f"{prefix}-track",
                "tool":"kdenlive_add_track",
                "arguments":{"audio":True,"name":f"Stem - {name}"},
            },
            {
                "id":f"{prefix}-import",
                "tool":"kdenlive_import_media",
                "arguments":{"path":str(path.resolve())},
            },
            {
                "id":f"{prefix}-insert",
                "tool":"kdenlive_insert_bin_clip",
                "arguments":{
                    "bin_id":{"$ref":f"{prefix}-import.result.bin_id"},
                    "track_id":{"$ref":f"{prefix}-track.result.track_id"},
                    "position_seconds":at,
                    "use_targets":False,
                },
            },
        ]
    if mute_original:
        steps.append({
            "id":"mute-original-audio",
            "tool":"kdenlive_set_clip_volume",
            "arguments":{
                "clip_id":{
                    "$clip_at":{
                        "track":{"audio":True,"index":original_audio_track_index},
                        "position_seconds":at+0.05,
                    }
                },
                "gain_db":-100.0,
            },
        })
    steps.append({"id":"save-after-stems","tool":"kdenlive_save_project","arguments":{}})
    return {
        "format":"update-p5-ai-edit",
        "version":1,
        "metadata":{
            "title":"Demucs stem separation",
            "generated_by":"Update P5 Demucs backend",
            "stems":{name:str(path.resolve()) for name,path in stems.items()},
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-demucs-stems"},
        "steps":steps,
    }


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Optional Demucs stem separation backend")
    p.add_argument("media",type=Path)
    p.add_argument("--python",dest="python_exe",default=sys.executable)
    p.add_argument("--model")
    p.add_argument("--two-stems",choices=("vocals","drums","bass","other"))
    p.add_argument("--device")
    p.add_argument("--jobs",type=int,default=0)
    p.add_argument("--output-dir",type=Path,required=True,help="Stable folder for copied stem files")
    p.add_argument("--plan-output",type=Path)
    p.add_argument("--at",type=float,default=0.0)
    p.add_argument("--original-audio-track-index",type=int,default=0)
    p.add_argument("--keep-original-audio",action="store_true")
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if not args.media.exists():
            raise DemucsError(f"Media file not found: {args.media}")
        temp_root=args.output_dir/"_demucs_raw"
        run_demucs(
            args.media,temp_root,
            python_exe=args.python_exe,
            model=args.model,
            two_stems=args.two_stems,
            device=args.device,
            jobs=args.jobs,
        )
        stems=stable_copy(discover_stems(temp_root,args.media),args.output_dir,args.media)
        shutil.rmtree(temp_root,ignore_errors=True)
        print("Stems:")
        for name,path in sorted(stems.items()):
            print(f"  {name}: {path}")
        if args.plan_output:
            plan=build_plan(
                stems,
                at=args.at,
                original_audio_track_index=args.original_audio_track_index,
                mute_original=not args.keep_original_audio,
            )
            args.plan_output.parent.mkdir(parents=True,exist_ok=True)
            args.plan_output.write_text(json.dumps(plan,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
            print(f"Wrote {args.plan_output}")
        return 0
    except (DemucsError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

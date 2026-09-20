#!/usr/bin/env python3
"""AI visual asset manifest for Update P5 Edit Aja.

Converts a B-roll plan into deterministic image/video generation jobs and can
resolve generated files back into the B-roll slot -> asset mapping format.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class AssetManifestError(RuntimeError):
    pass


DEFAULT_STYLE = (
    "realistic documentary editorial photography, cinematic but restrained, "
    "muted natural colors, believable lighting, clean composition, high detail, "
    "no visible text, no watermark, no logo"
)


def load_broll_plan(path: Path) -> dict[str, Any]:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssetManifestError(f"Invalid B-roll plan JSON: {exc}") from exc
    if not isinstance(data,dict) or data.get("format")!="update-p5-broll-plan":
        raise AssetManifestError("Expected update-p5-broll-plan JSON")
    return data


def _filename(slot_id:str,kind:str,ext:str)->str:
    safe=re.sub(r"[^A-Za-z0-9_-]+","-",slot_id).strip("-") or "asset"
    kind_safe=re.sub(r"[^A-Za-z0-9_-]+","-",kind).strip("-") or "visual"
    return f"{safe}-{kind_safe}.{ext}"


def media_defaults(kind:str)->tuple[str,str,str]:
    if kind in {"data_graphic","historical_map","quote_card","process_diagram_or_sequence"}:
        return "image","16:9","1920x1080"
    if kind in {"portrait_or_archival_person"}:
        return "image","16:9","1920x1080"
    return "image","16:9","1920x1080"


def make_manifest(
    plan:dict[str,Any],
    *,
    style_prefix:str=DEFAULT_STYLE,
    negative_suffix:str="avoid text labels, UI elements, watermarks, distorted anatomy",
)->dict[str,Any]:
    items=[]
    for slot in plan.get("slots",[]):
        if not isinstance(slot,dict):
            continue
        sid=str(slot.get("id",""))
        kind=str(slot.get("visual_type","illustrative_broll"))
        media_type,aspect,resolution=media_defaults(kind)
        hint=str(slot.get("prompt_hint") or slot.get("narration") or "").strip()
        prompt=", ".join(x for x in [style_prefix.strip(),hint,negative_suffix.strip()] if x)
        ext="png" if media_type=="image" else "mp4"
        items.append({
            "id":sid,
            "slot_id":sid,
            "media_type":media_type,
            "visual_type":kind,
            "timeline_start_seconds":slot.get("start_seconds"),
            "duration_seconds":slot.get("duration_seconds"),
            "aspect_ratio":aspect,
            "resolution":resolution,
            "prompt":prompt,
            "output_filename":_filename(sid,kind,ext),
            "status":"needed",
        })
    return {
        "format":"update-p5-ai-asset-manifest",
        "version":1,
        "style_prefix":style_prefix,
        "items":items,
        "summary":{"asset_count":len(items)},
    }


def resolve_folder(
    manifest:dict[str,Any],
    folder:Path,
    *,
    allow_extensions:tuple[str,...]=(".png",".jpg",".jpeg",".webp",".mp4",".mov",".mkv",".webm"),
)->tuple[dict[str,str],dict[str,Any]]:
    if not folder.exists():
        raise AssetManifestError(f"Asset folder not found: {folder}")
    mapping={}
    found=[]
    missing=[]
    by_stem={p.stem:p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in allow_extensions}
    by_name={p.name:p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in allow_extensions}
    for item in manifest.get("items",[]):
        if not isinstance(item,dict):
            continue
        slot=str(item.get("slot_id",item.get("id","")))
        expected=str(item.get("output_filename",""))
        candidate=by_name.get(expected)
        if candidate is None and expected:
            candidate=by_stem.get(Path(expected).stem)
        if candidate is None:
            # Accept any file beginning with the stable slot id.
            candidate=next((p for p in by_name.values() if p.stem.startswith(slot+"-") or p.stem==slot),None)
        if candidate is None:
            missing.append(slot)
            continue
        mapping[slot]=str(candidate.resolve())
        found.append({"slot_id":slot,"path":str(candidate.resolve())})
    report={
        "format":"update-p5-ai-asset-resolution",
        "version":1,
        "folder":str(folder.resolve()),
        "found":found,
        "missing":missing,
        "summary":{"found":len(found),"missing":len(missing)},
    }
    return mapping,report


def load_manifest(path:Path)->dict[str,Any]:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssetManifestError(f"Invalid asset manifest JSON: {exc}") from exc
    if not isinstance(data,dict) or data.get("format")!="update-p5-ai-asset-manifest":
        raise AssetManifestError("Expected update-p5-ai-asset-manifest JSON")
    return data


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Create/resolve AI visual asset manifests")
    sub=p.add_subparsers(dest="command",required=True)
    make=sub.add_parser("make")
    make.add_argument("broll_plan",type=Path)
    make.add_argument("--style-prefix",default=DEFAULT_STYLE)
    make.add_argument("--negative-suffix",default="avoid text labels, UI elements, watermarks, distorted anatomy")
    make.add_argument("--output",type=Path,required=True)
    resolve=sub.add_parser("resolve")
    resolve.add_argument("manifest",type=Path)
    resolve.add_argument("folder",type=Path)
    resolve.add_argument("--asset-map",type=Path,required=True)
    resolve.add_argument("--report",type=Path)
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=="make":
            data=make_manifest(
                load_broll_plan(args.broll_plan),
                style_prefix=args.style_prefix,
                negative_suffix=args.negative_suffix,
            )
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
            print(f"Wrote {args.output} ({data['summary']['asset_count']} assets)")
        else:
            mapping,report=resolve_folder(load_manifest(args.manifest),args.folder)
            args.asset_map.parent.mkdir(parents=True,exist_ok=True)
            args.asset_map.write_text(json.dumps(mapping,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
            if args.report:
                args.report.parent.mkdir(parents=True,exist_ok=True)
                args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
            print(f"Wrote {args.asset_map} ({len(mapping)} resolved assets)")
        return 0
    except (AssetManifestError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

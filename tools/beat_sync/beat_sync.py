#!/usr/bin/env python3
"""Beat-synchronized native cut planner for Update P5 Edit Aja."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class BeatEditError(RuntimeError):
    pass


def load_beats(path: Path) -> list[dict[str, float]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BeatEditError(f"Invalid rhythm JSON: {exc}") from exc
    beats = None
    if isinstance(data, dict):
        audio = data.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("beats"), list):
            beats = audio["beats"]
        elif isinstance(data.get("beats"), list):
            beats = data["beats"]
    if not isinstance(beats, list):
        raise BeatEditError("Could not find beats array in rhythm analysis")
    out=[]
    for item in beats:
        if not isinstance(item,dict):
            continue
        try:
            t=float(item["time_seconds"])
            strength=float(item.get("strength",0.0))
        except (KeyError,TypeError,ValueError):
            continue
        if t>0:
            out.append({"time_seconds":t,"strength":strength})
    out.sort(key=lambda x:x["time_seconds"])
    if not out:
        raise BeatEditError("No usable beats found")
    return out


def select_beats(
    beats:list[dict[str,float]],
    *,
    every:int=1,
    min_strength:float|None=None,
    start:float=0.0,
    end:float|None=None,
    offset:int=0,
)->list[dict[str,float]]:
    if every<1:
        raise BeatEditError("every must be >= 1")
    filtered=[
        b for b in beats
        if b["time_seconds"]>=start
        and (end is None or b["time_seconds"]<=end)
        and (min_strength is None or b["strength"]>=min_strength)
    ]
    return [b for i,b in enumerate(filtered) if (i-offset)%every==0]


def build_cut_plan(
    beats:list[dict[str,float]],
    *,
    video_track_index:int=0,
    title:str="Beat sync cuts",
)->dict[str,Any]:
    track={"audio":False,"index":video_track_index}
    steps=[]
    for i,beat in enumerate(beats,1):
        t=round(float(beat["time_seconds"]),6)
        steps.append({
            "id":f"beat-cut-{i:04d}",
            "tool":"kdenlive_cut_clip",
            "arguments":{
                "clip_id":{"$clip_at":{"track":track,"position_seconds":t}},
                "position_seconds":t,
            },
        })
    steps.append({"id":"save-after-beat-cuts","tool":"kdenlive_save_project","arguments":{}})
    return {
        "format":"update-p5-ai-edit",
        "version":1,
        "metadata":{
            "title":title,
            "generated_by":"Update P5 Beat Sync Editing",
            "cut_count":len(beats),
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-beat-sync-cuts"},
        "steps":steps,
    }


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Generate native timeline cuts from detected beats")
    p.add_argument("rhythm_analysis",type=Path)
    p.add_argument("--every",type=int,default=1,help="Use every Nth beat")
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--min-strength",type=float)
    p.add_argument("--start",type=float,default=0.0)
    p.add_argument("--end",type=float)
    p.add_argument("--video-track-index",type=int,default=0)
    p.add_argument("--output",type=Path,required=True)
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        beats=load_beats(args.rhythm_analysis)
        selected=select_beats(
            beats,
            every=args.every,
            min_strength=args.min_strength,
            start=args.start,
            end=args.end,
            offset=args.offset,
        )
        if not selected:
            raise BeatEditError("No beats remain after selection")
        plan=build_cut_plan(selected,video_track_index=args.video_track_index)
        plan["metadata"]["selection"]={
            "every":args.every,
            "offset":args.offset,
            "min_strength":args.min_strength,
            "start":args.start,
            "end":args.end,
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(plan,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"Wrote {args.output} ({len(selected)} beat cuts)")
        return 0
    except (BeatEditError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

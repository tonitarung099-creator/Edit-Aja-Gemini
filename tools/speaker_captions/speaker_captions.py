#!/usr/bin/env python3
"""Speaker-aware subtitle planner for Update P5 Edit Aja."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


class SpeakerCaptionError(RuntimeError):
    pass


def load_segments(path: Path) -> list[dict[str, Any]]:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpeakerCaptionError(f"Invalid transcript JSON: {exc}") from exc
    if isinstance(data,dict):
        data=data.get("segments",data.get("transcription"))
    if not isinstance(data,list) or not data:
        raise SpeakerCaptionError("Transcript must contain a non-empty segments array")
    out=[]
    current_speaker="Speaker 1"
    speaker_index=1
    for item in data:
        if not isinstance(item,dict):
            continue
        try:
            start=float(item.get("start_seconds",item.get("start")))
            end=float(item.get("end_seconds",item.get("end")))
        except (TypeError,ValueError):
            continue
        text=str(item.get("text","")).strip()
        if end<=start or not text:
            continue
        explicit=item.get("speaker")
        speaker=str(explicit).strip() if explicit is not None and str(explicit).strip() else current_speaker
        out.append({
            "start_seconds":start,
            "end_seconds":end,
            "text":text,
            "speaker":speaker,
        })
        if bool(item.get("speaker_turn_next")) and explicit is None:
            speaker_index = 2 if speaker_index == 1 else 1
            current_speaker=f"Speaker {speaker_index}"
    if not out:
        raise SpeakerCaptionError("No valid timestamped transcript segments found")
    return out


def load_styles(path: Path|None)->dict[str,dict[str,Any]]:
    if path is None:
        return {}
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpeakerCaptionError(f"Invalid speaker style JSON: {exc}") from exc
    if not isinstance(data,dict):
        raise SpeakerCaptionError("Speaker style config must be an object")
    result={}
    for speaker,value in data.items():
        if isinstance(value,str):
            result[str(speaker)]={"style":value}
        elif isinstance(value,dict):
            result[str(speaker)]=dict(value)
    return result


def build_plan(
    segments:list[dict[str,Any]],
    *,
    styles:dict[str,dict[str,Any]]|None=None,
    default_style:str="Default",
    base_layer:int=0,
)->dict[str,Any]:
    styles=styles or {}
    grouped:dict[str,list[dict[str,Any]]]=defaultdict(list)
    speaker_order=[]
    for seg in segments:
        speaker=str(seg["speaker"])
        if speaker not in grouped:
            speaker_order.append(speaker)
        grouped[speaker].append({
            "start_seconds":round(float(seg["start_seconds"]),6),
            "end_seconds":round(float(seg["end_seconds"]),6),
            "text":str(seg["text"]),
        })
    steps=[]
    mapping={}
    for i,speaker in enumerate(speaker_order):
        cfg=styles.get(speaker,{})
        layer=int(cfg.get("layer",base_layer+i))
        style=str(cfg.get("style",default_style))
        mapping[speaker]={"layer":layer,"style":style,"count":len(grouped[speaker])}
        safe="".join(ch.lower() if ch.isalnum() else "-" for ch in speaker).strip("-") or f"speaker-{i+1}"
        steps.append({
            "id":f"speaker-caption-{safe}",
            "tool":"kdenlive_add_subtitle_batch",
            "arguments":{
                "segments":grouped[speaker],
                "layer":layer,
                "style":style,
            },
        })
    steps.append({"id":"save-after-speaker-captions","tool":"kdenlive_save_project","arguments":{}})
    return {
        "format":"update-p5-ai-edit",
        "version":1,
        "metadata":{
            "title":"Speaker-aware captions",
            "generated_by":"Update P5 Speaker Captions",
            "speakers":mapping,
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-speaker-captions"},
        "steps":steps,
    }


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Create speaker-aware native subtitle batches")
    p.add_argument("transcript",type=Path)
    p.add_argument("--styles",type=Path,help="JSON mapping speaker -> style/layer")
    p.add_argument("--default-style",default="Default")
    p.add_argument("--base-layer",type=int,default=0)
    p.add_argument("--output",type=Path,required=True)
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        segments=load_segments(args.transcript)
        styles=load_styles(args.styles)
        plan=build_plan(
            segments,
            styles=styles,
            default_style=args.default_style,
            base_layer=args.base_layer,
        )
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(plan,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"Wrote {args.output} ({len(plan['metadata']['speakers'])} speakers)")
        return 0
    except (SpeakerCaptionError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

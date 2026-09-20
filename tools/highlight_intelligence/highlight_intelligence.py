#!/usr/bin/env python3
"""Highlight / social-clip intelligence for Update P5 Edit Aja.

Generates reviewable candidate windows from timestamped transcript segments and
can compile one approved candidate into a native remove-outside-range plan.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


class HighlightError(RuntimeError):
    pass


HOOK_PATTERNS = [
    (re.compile(r"\b(ternyata|faktanya|yang mengejutkan|masalahnya|rahasia|mengapa|kenapa|bagaimana)\b", re.I), 1.4, "hook_language"),
    (re.compile(r"\b(but|however|here'?s why|the problem|surprisingly|why|how)\b", re.I), 1.3, "hook_language"),
    (re.compile(r"\b(?:1[5-9]\d{2}|20\d{2}|\d+(?:[.,]\d+)?%)\b"), 0.7, "number_or_date"),
]


def load_segments(path: Path) -> list[dict[str, Any]]:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HighlightError(f"Invalid transcript JSON: {exc}") from exc
    if isinstance(data,dict):
        data=data.get("segments",data.get("transcription"))
    if not isinstance(data,list):
        raise HighlightError("Transcript must contain a segments array")
    out=[]
    for i,item in enumerate(data):
        if not isinstance(item,dict):
            continue
        try:
            start=float(item.get("start_seconds",item.get("start")))
            end=float(item.get("end_seconds",item.get("end")))
        except (TypeError,ValueError):
            continue
        text=str(item.get("text","")).strip()
        if end>start and text:
            out.append({"source_index":i,"start_seconds":start,"end_seconds":end,"text":text})
    out.sort(key=lambda x:x["start_seconds"])
    if not out:
        raise HighlightError("No valid timestamped segments")
    return out


def text_score(text:str,duration:float)->tuple[float,list[str]]:
    score=0.0
    reasons=[]
    if "?" in text:
        score+=0.8; reasons.append("question")
    if "!" in text:
        score+=0.35; reasons.append("emphasis")
    for pattern,weight,reason in HOOK_PATTERNS:
        if pattern.search(text):
            score+=weight
            if reason not in reasons:
                reasons.append(reason)
    words=len(re.findall(r"\w+",text,re.UNICODE))
    if 45<=words<=140:
        score+=0.7; reasons.append("dense_explanation")
    elif words>=25:
        score+=0.35; reasons.append("substantial_explanation")
    if 20<=duration<=45:
        score+=0.8; reasons.append("social_length")
    elif 12<=duration<=60:
        score+=0.35; reasons.append("usable_length")
    return score,reasons


def candidates(
    segments:list[dict[str,Any]],
    *,
    min_duration:float=20.0,
    target_duration:float=35.0,
    max_duration:float=60.0,
    max_candidates:int=8,
)->dict[str,Any]:
    if min_duration<=0 or target_duration<min_duration or max_duration<target_duration:
        raise HighlightError("Require 0 < min_duration <= target_duration <= max_duration")
    raw=[]
    for i in range(len(segments)):
        start=segments[i]["start_seconds"]
        text_parts=[]
        end=start
        for j in range(i,len(segments)):
            seg=segments[j]
            end=seg["end_seconds"]
            duration=end-start
            if duration>max_duration:
                break
            text_parts.append(seg["text"])
            if duration>=min_duration:
                text=" ".join(text_parts)
                score,reasons=text_score(text,duration)
                closeness=max(0.0,1.0-abs(duration-target_duration)/max(target_duration,1.0))
                score+=0.6*closeness
                raw.append({
                    "start_seconds":start,
                    "end_seconds":end,
                    "duration_seconds":duration,
                    "text":text,
                    "score":score,
                    "reasons":reasons+["target_duration_fit"],
                    "source_start_index":segments[i]["source_index"],
                    "source_end_index":segments[j]["source_index"],
                })
    raw.sort(key=lambda x:(x["score"],-abs(x["duration_seconds"]-target_duration)),reverse=True)
    selected=[]
    for item in raw:
        if any(
            min(item["end_seconds"],x["end_seconds"])-max(item["start_seconds"],x["start_seconds"])
            > 0.45*min(item["duration_seconds"],x["duration_seconds"])
            for x in selected
        ):
            continue
        item=dict(item)
        item["id"]=f"highlight-{len(selected)+1:03d}"
        item["score"]=round(float(item["score"]),3)
        selected.append(item)
        if len(selected)>=max_candidates:
            break
    return {
        "format":"update-p5-highlight-review",
        "version":1,
        "candidates":selected,
        "summary":{
            "candidate_count":len(selected),
            "transcript_end_seconds":segments[-1]["end_seconds"],
        },
    }


def to_ai_edit(
    report:dict[str,Any],
    candidate_id:str,
    *,
    padding:float=0.15,
    video_track_index:int=0,
    audio_track_index:int=0,
)->dict[str,Any]:
    item=next((x for x in report.get("candidates",[]) if x.get("id")==candidate_id),None)
    if not isinstance(item,dict):
        raise HighlightError(f"Highlight candidate not found: {candidate_id}")
    total=float(report.get("summary",{}).get("transcript_end_seconds",item["end_seconds"]))
    start=max(0.0,float(item["start_seconds"])-padding)
    end=min(total,float(item["end_seconds"])+padding)
    ranges=[]
    if start>0:
        ranges.append({"start_seconds":0.0,"end_seconds":start})
    if end<total:
        ranges.append({"start_seconds":end,"end_seconds":total})
    return {
        "format":"update-p5-ai-edit",
        "version":1,
        "metadata":{
            "title":f"Highlight clip {candidate_id}",
            "generated_by":"Update P5 Highlight Intelligence",
            "candidate_id":candidate_id,
            "highlight_duration_seconds":end-start,
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-highlight-extract"},
        "steps":[
            {
                "id":"keep-highlight-only",
                "tool":"kdenlive_remove_ranges",
                "arguments":{
                    "track_ids":[
                        {"$track":{"audio":False,"index":video_track_index}},
                        {"$track":{"audio":True,"index":audio_track_index}},
                    ],
                    "ranges":ranges,
                    "lift_only":False,
                    "dry_run":False,
                },
            },
            {"id":"save-highlight","tool":"kdenlive_save_project","arguments":{}},
        ],
    }


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Find reviewable highlight/social clip candidates")
    sub=p.add_subparsers(dest="command",required=True)
    scan=sub.add_parser("scan")
    scan.add_argument("transcript",type=Path)
    scan.add_argument("--min-duration",type=float,default=20.0)
    scan.add_argument("--target-duration",type=float,default=35.0)
    scan.add_argument("--max-duration",type=float,default=60.0)
    scan.add_argument("--max-candidates",type=int,default=8)
    scan.add_argument("--output",type=Path,required=True)
    comp=sub.add_parser("compile")
    comp.add_argument("review",type=Path)
    comp.add_argument("candidate_id")
    comp.add_argument("--padding",type=float,default=0.15)
    comp.add_argument("--video-track-index",type=int,default=0)
    comp.add_argument("--audio-track-index",type=int,default=0)
    comp.add_argument("--output",type=Path,required=True)
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=="scan":
            data=candidates(
                load_segments(args.transcript),
                min_duration=args.min_duration,
                target_duration=args.target_duration,
                max_duration=args.max_duration,
                max_candidates=args.max_candidates,
            )
        else:
            try:
                report=json.loads(args.review.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise HighlightError(f"Invalid review JSON: {exc}") from exc
            if not isinstance(report,dict) or report.get("format")!="update-p5-highlight-review":
                raise HighlightError("Expected update-p5-highlight-review JSON")
            data=to_ai_edit(
                report,args.candidate_id,
                padding=args.padding,
                video_track_index=args.video_track_index,
                audio_track_index=args.audio_track_index,
            )
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (HighlightError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

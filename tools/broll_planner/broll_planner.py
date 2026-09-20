#!/usr/bin/env python3
"""Transcript-driven B-roll planner for Update P5 Edit Aja.

Creates visual slots from narration transcript. It is intentionally deterministic:
it suggests visual types and prompt hints, while ChatGPT or another model can
later enrich the prompts or provide final asset paths.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


class BrollError(RuntimeError):
    pass


YEAR_RE = re.compile(r"\b(?:1[5-9]\d{2}|20\d{2})\b")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
QUOTE_RE = re.compile(r'["“”][^"“”]{8,}["“”]')
LOCATION_WORDS = {
    "negara", "kota", "pulau", "gunung", "laut", "wilayah", "provinsi",
    "jepang", "indonesia", "asia", "eropa", "amerika", "tokyo", "osaka",
    "country", "city", "island", "region", "world", "map",
}
PROCESS_WORDS = {
    "proses", "dibangun", "membentuk", "berubah", "berkembang", "tahap",
    "process", "built", "formed", "changed", "developed", "stage",
}
PERSON_WORDS = {
    "raja", "kaisar", "presiden", "pemimpin", "tokoh", "ilmuwan", "samurai",
    "king", "emperor", "president", "leader", "scientist",
}


def load_segments(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrollError(f"Invalid transcript JSON: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("segments", data.get("transcription"))
    if not isinstance(data, list):
        raise BrollError("Transcript must contain a segments array")
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
        raise BrollError("No valid timestamped transcript segments")
    return out


def visual_type(text: str) -> tuple[str, list[str]]:
    lowered=text.lower()
    words=set(re.findall(r"\w+",lowered,re.UNICODE))
    reasons=[]
    if QUOTE_RE.search(text):
        return "quote_card",["quoted_language"]
    if YEAR_RE.search(text):
        reasons.append("year_or_historical_date")
        if words & LOCATION_WORDS:
            return "historical_map",reasons+["location_context"]
        return "archive_history",reasons
    if NUMBER_RE.search(text):
        return "data_graphic",["numeric_claim"]
    if words & LOCATION_WORDS:
        return "map_or_establishing_shot",["location_context"]
    if words & PERSON_WORDS:
        return "portrait_or_archival_person",["person_context"]
    if words & PROCESS_WORDS:
        return "process_diagram_or_sequence",["process_context"]
    return "illustrative_broll",["general_narration"]


def prompt_hint(text: str, kind: str) -> str:
    cleaned=re.sub(r"\s+"," ",text).strip()
    prefixes={
        "quote_card":"documentary quote/source card based on",
        "historical_map":"historical documentary map visual illustrating",
        "archive_history":"historically inspired archival/documentary visual illustrating",
        "data_graphic":"clean documentary data visualization illustrating",
        "map_or_establishing_shot":"documentary establishing visual or map illustrating",
        "portrait_or_archival_person":"historical/editorial portrait or archival-style visual illustrating",
        "process_diagram_or_sequence":"clean documentary process visual explaining",
        "illustrative_broll":"realistic documentary B-roll visual illustrating",
    }
    return f"{prefixes.get(kind,'documentary visual illustrating')}: {cleaned}"


def plan_slots(
    segments:list[dict[str,Any]],
    *,
    minimum_gap:float=3.0,
    default_duration:float=4.0,
    maximum_duration:float=6.0,
    start_after:float=0.0,
    end_before:float|None=None,
)->dict[str,Any]:
    slots=[]
    last_end=-1e9
    for seg in segments:
        start=float(seg["start_seconds"])
        end=float(seg["end_seconds"])
        if start<start_after:
            continue
        if end_before is not None and start>=end_before:
            break
        if start-last_end<minimum_gap:
            continue
        kind,reasons=visual_type(seg["text"])
        duration=max(1.0,min(maximum_duration,max(default_duration,end-start)))
        slot_end=start+duration
        if end_before is not None:
            slot_end=min(slot_end,end_before)
        if slot_end<=start:
            continue
        slot_id=f"broll-{len(slots)+1:04d}"
        slots.append({
            "id":slot_id,
            "start_seconds":round(start,6),
            "end_seconds":round(slot_end,6),
            "duration_seconds":round(slot_end-start,6),
            "narration":seg["text"],
            "visual_type":kind,
            "reasons":reasons,
            "prompt_hint":prompt_hint(seg["text"],kind),
            "asset":None,
            "status":"planned",
            "source_index":seg["source_index"],
        })
        last_end=slot_end
    return {
        "format":"update-p5-broll-plan",
        "version":1,
        "slots":slots,
        "summary":{
            "slot_count":len(slots),
            "planned_seconds":round(sum(x["duration_seconds"] for x in slots),6),
        },
    }


def to_placeholder_ai_edit(plan:dict[str,Any])->dict[str,Any]:
    steps=[]
    for slot in plan.get("slots",[]):
        sid=str(slot["id"])
        track_id=f"{sid}-track"
        steps.append({
            "id":track_id,
            "tool":"kdenlive_add_track",
            "arguments":{"audio":False,"name":f"B-roll {sid}"},
        })
        label=f"{slot['visual_type'].upper()}\n{slot['narration']}"
        steps.append({
            "id":f"{sid}-placeholder",
            "tool":"kdenlive_create_title",
            "arguments":{
                "text":label,
                "name":f"B-roll placeholder {sid}",
                "duration_seconds":slot["duration_seconds"],
                "track_id":{"$ref":f"{track_id}.result.track_id"},
                "position_seconds":slot["start_seconds"],
                "font_size":34,
                "font_color":"#FFFFFFFF",
                "outline_color":"#000000FF",
                "outline_width":2,
                "bold":True,
                "x":80,
                "y":100,
            },
        })
    steps.append({"id":"save-after-broll-placeholders","tool":"kdenlive_save_project","arguments":{}})
    return {
        "format":"update-p5-ai-edit",
        "version":1,
        "metadata":{
            "title":"Transcript B-roll placeholders",
            "generated_by":"Update P5 B-roll Planner",
            "slot_count":len(plan.get("slots",[])),
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-broll-placeholders"},
        "steps":steps,
    }


def load_asset_map(path:Path)->dict[str,str]:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrollError(f"Invalid asset map JSON: {exc}") from exc
    if not isinstance(data,dict):
        raise BrollError("Asset map must be an object mapping slot id to file path")
    return {str(k):str(v) for k,v in data.items() if str(v).strip()}


def to_asset_ai_edit(plan:dict[str,Any],assets:dict[str,str])->dict[str,Any]:
    steps=[]
    inserted=0
    for slot in plan.get("slots",[]):
        sid=str(slot["id"])
        asset=assets.get(sid)
        if not asset:
            continue
        prefix=sid
        steps.extend([
            {
                "id":f"{prefix}-track",
                "tool":"kdenlive_add_track",
                "arguments":{"audio":False,"name":f"B-roll {sid}"},
            },
            {
                "id":f"{prefix}-import",
                "tool":"kdenlive_import_media",
                "arguments":{"path":asset},
            },
            {
                "id":f"{prefix}-insert",
                "tool":"kdenlive_insert_bin_clip",
                "arguments":{
                    "bin_id":{"$ref":f"{prefix}-import.result.bin_id"},
                    "track_id":{"$ref":f"{prefix}-track.result.track_id"},
                    "position_seconds":slot["start_seconds"],
                    "use_targets":False,
                },
            },
            {
                "id":f"{prefix}-resize",
                "tool":"kdenlive_resize_item",
                "arguments":{
                    "item_id":{
                        "$clip_at":{
                            "track_id":{"$ref":f"{prefix}-track.result.track_id"},
                            "position_seconds":slot["start_seconds"]+min(0.05,slot["duration_seconds"]/4),
                        }
                    },
                    "duration_seconds":slot["duration_seconds"],
                    "edge":"right",
                    "allow_single_resize":True,
                },
            },
        ])
        inserted+=1
    steps.append({"id":"save-after-broll-assets","tool":"kdenlive_save_project","arguments":{}})
    return {
        "format":"update-p5-ai-edit",
        "version":1,
        "metadata":{
            "title":"Resolved B-roll assets",
            "generated_by":"Update P5 B-roll Planner",
            "inserted_assets":inserted,
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-broll-assets"},
        "steps":steps,
    }


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Plan transcript-driven B-roll and compile timeline placeholders/assets")
    sub=p.add_subparsers(dest="command",required=True)

    scan=sub.add_parser("plan")
    scan.add_argument("transcript",type=Path)
    scan.add_argument("--minimum-gap",type=float,default=3.0)
    scan.add_argument("--default-duration",type=float,default=4.0)
    scan.add_argument("--maximum-duration",type=float,default=6.0)
    scan.add_argument("--start-after",type=float,default=0.0)
    scan.add_argument("--end-before",type=float)
    scan.add_argument("--output",type=Path,required=True)

    ph=sub.add_parser("placeholders")
    ph.add_argument("plan",type=Path)
    ph.add_argument("--output",type=Path,required=True)

    assets=sub.add_parser("assets")
    assets.add_argument("plan",type=Path)
    assets.add_argument("asset_map",type=Path)
    assets.add_argument("--output",type=Path,required=True)
    return p


def _load_plan(path:Path)->dict[str,Any]:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrollError(f"Invalid B-roll plan JSON: {exc}") from exc
    if not isinstance(data,dict) or data.get("format")!="update-p5-broll-plan":
        raise BrollError("Expected update-p5-broll-plan JSON")
    return data


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        if args.command=="plan":
            data=plan_slots(
                load_segments(args.transcript),
                minimum_gap=args.minimum_gap,
                default_duration=args.default_duration,
                maximum_duration=args.maximum_duration,
                start_after=args.start_after,
                end_before=args.end_before,
            )
        elif args.command=="placeholders":
            data=to_placeholder_ai_edit(_load_plan(args.plan))
        else:
            data=to_asset_ai_edit(_load_plan(args.plan),load_asset_map(args.asset_map))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (BrollError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

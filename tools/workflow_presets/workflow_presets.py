#!/usr/bin/env python3
"""Creator workflow preset generator for Update P5 Edit Aja."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class PresetError(RuntimeError):
    pass


PRESETS = ("documentary", "talking-head", "podcast", "shorts")


def _stage(
    stage_id: str,
    script: str,
    args: list[str],
    outputs: dict[str, str],
    *,
    plan_output: str | None = None,
    optional: bool = False,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": stage_id,
        "script": script,
        "args": args,
        "outputs": outputs,
    }
    if plan_output:
        data["plan_output"] = plan_output
    if optional:
        data["optional"] = True
    return data


def documentary(transcript: str, rhythm: str | None = None) -> dict[str, Any]:
    stages = [
        _stage(
            "captions",
            "tools/caption_intelligence/caption_intelligence.py",
            ["{{TRANSCRIPT}}","--mode","phrase","--format","ai-edit","--output","{{workdir}}/captions.edit.json"],
            {"plan":"{{workdir}}/captions.edit.json"},
            plan_output="{{captions.plan}}",
        ),
        _stage(
            "broll",
            "tools/broll_planner/broll_planner.py",
            ["plan","{{TRANSCRIPT}}","--output","{{workdir}}/broll-plan.json"],
            {"plan_data":"{{workdir}}/broll-plan.json"},
        ),
        _stage(
            "broll-placeholders",
            "tools/broll_planner/broll_planner.py",
            ["placeholders","{{broll.plan_data}}","--output","{{workdir}}/broll-placeholders.edit.json"],
            {"plan":"{{workdir}}/broll-placeholders.edit.json"},
            plan_output="{{broll-placeholders.plan}}",
        ),
        _stage(
            "bad-takes",
            "tools/bad_take_review/bad_take_review.py",
            ["scan","{{TRANSCRIPT}}","--output","{{workdir}}/bad-takes.review.json"],
            {"review":"{{workdir}}/bad-takes.review.json"},
        ),
    ]
    variables={"TRANSCRIPT":transcript}
    if rhythm:
        variables["RHYTHM"]=rhythm
        stages.append(
            _stage(
                "beat-cuts",
                "tools/beat_sync/beat_sync.py",
                ["{{RHYTHM}}","--every","4","--output","{{workdir}}/beat-cuts.edit.json"],
                {"plan":"{{workdir}}/beat-cuts.edit.json"},
                plan_output="{{beat-cuts.plan}}",
                optional=True,
            )
        )
    return {
        "title":"Documentary Creator Workflow",
        "variables":variables,
        "stages":stages,
        "compose":{"title":"Documentary Final Edit","output":"final.edit.json","collapse_saves":True},
    }


def talking_head(transcript: str) -> dict[str, Any]:
    return {
        "title":"Talking Head Workflow",
        "variables":{"TRANSCRIPT":transcript},
        "stages":[
            _stage(
                "captions",
                "tools/caption_intelligence/caption_intelligence.py",
                ["{{TRANSCRIPT}}","--mode","phrase","--max-words","5","--format","ai-edit","--output","{{workdir}}/captions.edit.json"],
                {"plan":"{{workdir}}/captions.edit.json"},
                plan_output="{{captions.plan}}",
            ),
            _stage(
                "dialogue-review",
                "tools/dialogue_intelligence/dialogue_intelligence.py",
                ["{{TRANSCRIPT}}","--format","report","--output","{{workdir}}/dialogue.review.json"],
                {"review":"{{workdir}}/dialogue.review.json"},
                optional=True,
            ),
            _stage(
                "bad-takes",
                "tools/bad_take_review/bad_take_review.py",
                ["scan","{{TRANSCRIPT}}","--output","{{workdir}}/bad-takes.review.json"],
                {"review":"{{workdir}}/bad-takes.review.json"},
            ),
            _stage(
                "highlights",
                "tools/highlight_intelligence/highlight_intelligence.py",
                ["scan","{{TRANSCRIPT}}","--output","{{workdir}}/highlights.review.json"],
                {"review":"{{workdir}}/highlights.review.json"},
            ),
        ],
        "compose":{"title":"Talking Head Base Edit","output":"final.edit.json","collapse_saves":True},
    }


def podcast(transcript: str) -> dict[str, Any]:
    return {
        "title":"Podcast Workflow",
        "variables":{"TRANSCRIPT":transcript},
        "stages":[
            _stage(
                "speaker-captions",
                "tools/speaker_captions/speaker_captions.py",
                ["{{TRANSCRIPT}}","--output","{{workdir}}/speaker-captions.edit.json"],
                {"plan":"{{workdir}}/speaker-captions.edit.json"},
                plan_output="{{speaker-captions.plan}}",
            ),
            _stage(
                "bad-takes",
                "tools/bad_take_review/bad_take_review.py",
                ["scan","{{TRANSCRIPT}}","--output","{{workdir}}/bad-takes.review.json"],
                {"review":"{{workdir}}/bad-takes.review.json"},
            ),
            _stage(
                "highlights",
                "tools/highlight_intelligence/highlight_intelligence.py",
                ["scan","{{TRANSCRIPT}}","--target-duration","45","--max-duration","75","--output","{{workdir}}/highlights.review.json"],
                {"review":"{{workdir}}/highlights.review.json"},
            ),
        ],
        "compose":{"title":"Podcast Base Edit","output":"final.edit.json","collapse_saves":True},
    }


def shorts(transcript: str, subject_track: str | None = None) -> dict[str, Any]:
    stages=[
        _stage(
            "animated-captions",
            "tools/animated_captions/animated_captions.py",
            ["{{TRANSCRIPT}}","--preset","pop","--output","{{workdir}}/animated-captions.edit.json"],
            {"plan":"{{workdir}}/animated-captions.edit.json"},
            plan_output="{{animated-captions.plan}}",
        ),
        _stage(
            "highlights",
            "tools/highlight_intelligence/highlight_intelligence.py",
            ["scan","{{TRANSCRIPT}}","--min-duration","15","--target-duration","30","--max-duration","60","--output","{{workdir}}/highlights.review.json"],
            {"review":"{{workdir}}/highlights.review.json"},
        ),
    ]
    variables={"TRANSCRIPT":transcript}
    if subject_track:
        variables["SUBJECT_TRACK"]=subject_track
        stages.append(
            _stage(
                "vertical-reframe",
                "tools/visual_intelligence/visual_intelligence.py",
                ["reframe","{{SUBJECT_TRACK}}","--preset","vertical","--output","{{workdir}}/vertical-reframe.edit.json"],
                {"plan":"{{workdir}}/vertical-reframe.edit.json"},
                plan_output="{{vertical-reframe.plan}}",
            )
        )
    return {
        "title":"Short-form Workflow",
        "variables":variables,
        "stages":stages,
        "compose":{"title":"Short-form Base Edit","output":"final.edit.json","collapse_saves":True},
    }


def make_preset(name:str,*,transcript:str,rhythm:str|None=None,subject_track:str|None=None)->dict[str,Any]:
    if name=="documentary":
        return documentary(transcript,rhythm)
    if name=="talking-head":
        return talking_head(transcript)
    if name=="podcast":
        return podcast(transcript)
    if name=="shorts":
        return shorts(transcript,subject_track)
    raise PresetError(f"Unknown preset: {name}")


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Generate Creator Pipeline configs from common editing presets")
    p.add_argument("preset",choices=PRESETS)
    p.add_argument("--transcript",required=True)
    p.add_argument("--rhythm")
    p.add_argument("--subject-track")
    p.add_argument("--workdir",default="./creator-output")
    p.add_argument("--output",type=Path,required=True)
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        data=make_preset(
            args.preset,
            transcript=args.transcript,
            rhythm=args.rhythm,
            subject_track=args.subject_track,
        )
        data["workdir"]=args.workdir
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"Wrote {args.output}")
        return 0
    except (PresetError,OSError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

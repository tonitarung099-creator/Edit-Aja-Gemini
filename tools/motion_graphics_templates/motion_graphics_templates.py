#!/usr/bin/env python3
"""Reusable editorial motion-graphics templates for Update P5 Edit Aja.

Each template is compiled to a short sequence of SVG stages plus a Phase 6 plan.
The stages emulate reveals/punch-ins while staying replaceable as ordinary
timeline media.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


class TemplateError(RuntimeError):
    pass


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def svg(width:int,height:int,body:str,bg:str="#101114")->str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="{esc(bg)}"/>{body}</svg>\n'
    )


def stat_stage(title:str,value:str,subtitle:str,source:str,stage:int,*,width:int=1920,height:int=1080)->str:
    body=[
        f'<text x="160" y="180" fill="#F5F5F5" font-size="48" font-family="sans-serif" font-weight="700">{esc(title)}</text>'
    ]
    if stage>=2:
        body.append(f'<text x="160" y="570" fill="#68A7FF" font-size="210" font-family="sans-serif" font-weight="800">{esc(value)}</text>')
    if stage>=3 and subtitle:
        body.append(f'<text x="170" y="690" fill="#F5F5F5" font-size="44" font-family="sans-serif">{esc(subtitle)}</text>')
    if stage>=4 and source:
        body.append(f'<text x="170" y="950" fill="#B8BDC8" font-size="28" font-family="sans-serif">Source: {esc(source)}</text>')
    return svg(width,height,"".join(body))


def comparison_stage(left:dict[str,Any],right:dict[str,Any],title:str,stage:int,*,width:int=1920,height:int=1080)->str:
    body=[
        f'<text x="140" y="140" fill="#F5F5F5" font-size="58" font-family="sans-serif" font-weight="700">{esc(title)}</text>',
        '<line x1="960" y1="220" x2="960" y2="900" stroke="#FFFFFF" stroke-opacity=".18" stroke-width="4"/>'
    ]
    if stage>=1:
        body += [
            f'<text x="200" y="360" fill="#F5F5F5" font-size="46" font-family="sans-serif" font-weight="700">{esc(left.get("label","A"))}</text>',
            f'<text x="200" y="560" fill="#68A7FF" font-size="150" font-family="sans-serif" font-weight="800">{esc(left.get("value",""))}</text>',
        ]
    if stage>=2:
        body += [
            f'<text x="1090" y="360" fill="#F5F5F5" font-size="46" font-family="sans-serif" font-weight="700">{esc(right.get("label","B"))}</text>',
            f'<text x="1090" y="560" fill="#FF8C68" font-size="150" font-family="sans-serif" font-weight="800">{esc(right.get("value",""))}</text>',
        ]
    if stage>=3:
        body += [
            f'<text x="200" y="690" fill="#DADDE3" font-size="34" font-family="sans-serif">{esc(left.get("detail",""))}</text>',
            f'<text x="1090" y="690" fill="#DADDE3" font-size="34" font-family="sans-serif">{esc(right.get("detail",""))}</text>',
        ]
    return svg(width,height,"".join(body))


def callout_stage(kicker:str,headline:str,body_text:str,stage:int,*,width:int=1920,height:int=1080)->str:
    body=[
        '<rect x="110" y="170" width="14" height="690" rx="7" fill="#68A7FF"/>',
        f'<text x="175" y="260" fill="#68A7FF" font-size="34" font-family="sans-serif" font-weight="700">{esc(kicker.upper())}</text>',
    ]
    if stage>=2:
        body.append(f'<text x="175" y="430" fill="#F5F5F5" font-size="86" font-family="sans-serif" font-weight="800">{esc(headline)}</text>')
    if stage>=3:
        body.append(f'<text x="180" y="560" fill="#DADDE3" font-size="38" font-family="sans-serif">{esc(body_text)}</text>')
    return svg(width,height,"".join(body))


def progress_stage(title:str,value:float,label:str,stage:int,*,width:int=1920,height:int=1080)->str:
    value=max(0.0,min(100.0,value))
    shown=value*(stage/4.0)
    bar_w=1400
    fill=bar_w*shown/100.0
    body=[
        f'<text x="220" y="290" fill="#F5F5F5" font-size="62" font-family="sans-serif" font-weight="700">{esc(title)}</text>',
        '<rect x="220" y="500" width="1400" height="90" rx="45" fill="#252A32"/>',
        f'<rect x="220" y="500" width="{fill:.2f}" height="90" rx="45" fill="#68A7FF"/>',
        f'<text x="220" y="710" fill="#F5F5F5" font-size="96" font-family="sans-serif" font-weight="800">{shown:.0f}%</text>',
        f'<text x="520" y="705" fill="#C9CDD5" font-size="40" font-family="sans-serif">{esc(label)}</text>',
    ]
    return svg(width,height,"".join(body))


def stages_for(item:dict[str,Any])->list[str]:
    kind=str(item.get("type",""))
    width=int(item.get("width",1920)); height=int(item.get("height",1080))
    if kind=="stat_reveal":
        return [
            stat_stage(str(item.get("title","")),str(item.get("value","")),str(item.get("subtitle","")),str(item.get("source","")),i,width=width,height=height)
            for i in range(1,5)
        ]
    if kind=="comparison":
        left=item.get("left",{}); right=item.get("right",{})
        if not isinstance(left,dict) or not isinstance(right,dict):
            raise TemplateError("comparison requires left/right objects")
        return [comparison_stage(left,right,str(item.get("title","Comparison")),i,width=width,height=height) for i in range(1,4)]
    if kind=="callout":
        return [
            callout_stage(str(item.get("kicker","Context")),str(item.get("headline","")),str(item.get("body","")),i,width=width,height=height)
            for i in range(1,4)
        ]
    if kind=="progress":
        value=float(item.get("value",0))
        return [progress_stage(str(item.get("title","Progress")),value,str(item.get("label","")),i,width=width,height=height) for i in range(1,5)]
    raise TemplateError(f"Unsupported motion template: {kind!r}")


def compile_templates(config:dict[str,Any],output_dir:Path)->tuple[list[Path],dict[str,Any]]:
    items=config.get("templates")
    if not isinstance(items,list) or not items:
        raise TemplateError("Config requires a non-empty templates array")
    output_dir.mkdir(parents=True,exist_ok=True)
    assets=[]
    steps=[]
    for idx,item in enumerate(items,1):
        if not isinstance(item,dict):
            raise TemplateError(f"templates[{idx-1}] must be an object")
        kind=str(item.get("type",""))
        at=float(item.get("at",0.0))
        duration=float(item.get("duration",4.0))
        if duration<=0:
            raise TemplateError("template duration must be positive")
        stages=stages_for(item)
        stage_duration=duration/len(stages)
        prefix=f"motion-{idx:03d}"
        steps.append({
            "id":f"{prefix}-track",
            "tool":"kdenlive_add_track",
            "arguments":{"audio":False,"name":str(item.get("track_name","Motion Graphics"))},
        })
        for sidx,content in enumerate(stages,1):
            asset=output_dir/f"{prefix}-{kind}-stage-{sidx:02d}.svg"
            asset.write_text(content,encoding="utf-8")
            assets.append(asset)
            sid=f"{prefix}-s{sidx:02d}"
            start=at+(sidx-1)*stage_duration
            steps += [
                {"id":f"{sid}-import","tool":"kdenlive_import_media","arguments":{"path":str(asset.resolve())}},
                {
                    "id":f"{sid}-insert","tool":"kdenlive_insert_bin_clip",
                    "arguments":{
                        "bin_id":{"$ref":f"{sid}-import.result.bin_id"},
                        "track_id":{"$ref":f"{prefix}-track.result.track_id"},
                        "position_seconds":round(start,6),
                        "use_targets":False,
                    },
                },
                {
                    "id":f"{sid}-duration","tool":"kdenlive_resize_item",
                    "arguments":{
                        "item_id":{
                            "$clip_at":{
                                "track_id":{"$ref":f"{prefix}-track.result.track_id"},
                                "position_seconds":round(start+min(0.03,stage_duration/4),6),
                            }
                        },
                        "duration_seconds":round(stage_duration,6),
                        "edge":"right",
                        "allow_single_resize":True,
                    },
                },
            ]
    steps.append({"id":"save-after-motion-templates","tool":"kdenlive_save_project","arguments":{}})
    plan={
        "format":"update-p5-ai-edit","version":1,
        "metadata":{
            "title":str(config.get("title","Editorial motion graphics")),
            "generated_by":"Update P5 Motion Graphics Templates",
            "template_count":len(items),
            "asset_count":len(assets),
        },
        "safety":{"checkpoint":True,"checkpoint_label":"before-motion-graphics"},
        "steps":steps,
    }
    return assets,plan


def build_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Compile reusable editorial motion graphics")
    p.add_argument("config",type=Path)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--plan-output",type=Path,required=True)
    return p


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try:
        try:
            cfg=json.loads(args.config.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TemplateError(f"Invalid config JSON: {exc}") from exc
        if not isinstance(cfg,dict):
            raise TemplateError("Config root must be an object")
        assets,plan=compile_templates(cfg,args.output_dir)
        args.plan_output.parent.mkdir(parents=True,exist_ok=True)
        args.plan_output.write_text(json.dumps(plan,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(f"Wrote {len(assets)} SVG stages and {args.plan_output}")
        return 0
    except (TemplateError,OSError,TypeError,ValueError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())

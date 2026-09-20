import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "speaker_captions" / "speaker_captions.py"
spec = importlib.util.spec_from_file_location("speaker_captions", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class SpeakerCaptionTests(unittest.TestCase):
    def test_explicit_speakers(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.json"
            p.write_text(json.dumps({"segments":[
                {"start_seconds":0,"end_seconds":1,"text":"Hi","speaker":"A"},
                {"start_seconds":1,"end_seconds":2,"text":"Hello","speaker":"B"}
            ]}),encoding="utf-8")
            got=mod.load_segments(p)
            self.assertEqual([x["speaker"] for x in got],["A","B"])

    def test_turn_next_alternates(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.json"
            p.write_text(json.dumps({"segments":[
                {"start_seconds":0,"end_seconds":1,"text":"One","speaker_turn_next":True},
                {"start_seconds":1,"end_seconds":2,"text":"Two","speaker_turn_next":True},
                {"start_seconds":2,"end_seconds":3,"text":"Three"}
            ]}),encoding="utf-8")
            got=mod.load_segments(p)
            self.assertEqual([x["speaker"] for x in got],["Speaker 1","Speaker 2","Speaker 1"])

    def test_plan_groups_layers(self):
        segs=[
            {"start_seconds":0,"end_seconds":1,"text":"Hi","speaker":"A"},
            {"start_seconds":1,"end_seconds":2,"text":"Yo","speaker":"B"},
            {"start_seconds":2,"end_seconds":3,"text":"Again","speaker":"A"},
        ]
        plan=mod.build_plan(segs,styles={"A":{"style":"StyleA","layer":3}})
        self.assertEqual(plan["format"],"update-p5-ai-edit")
        self.assertEqual(plan["metadata"]["speakers"]["A"]["count"],2)
        a=next(x for x in plan["steps"] if x["id"]=="speaker-caption-a")
        self.assertEqual(a["arguments"]["layer"],3)
        self.assertEqual(a["arguments"]["style"],"StyleA")


if __name__=="__main__":
    unittest.main()

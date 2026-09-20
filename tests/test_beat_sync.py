import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "beat_sync" / "beat_sync.py"
spec = importlib.util.spec_from_file_location("beat_sync", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class BeatSyncTests(unittest.TestCase):
    def test_select_every_second_beat(self):
        beats=[{"time_seconds":float(i),"strength":1.0} for i in range(1,7)]
        got=mod.select_beats(beats,every=2)
        self.assertEqual([x["time_seconds"] for x in got],[1.0,3.0,5.0])

    def test_strength_filter(self):
        beats=[
            {"time_seconds":1.0,"strength":0.1},
            {"time_seconds":2.0,"strength":0.8},
            {"time_seconds":3.0,"strength":0.9},
        ]
        got=mod.select_beats(beats,min_strength=0.5)
        self.assertEqual(len(got),2)

    def test_build_plan(self):
        plan=mod.build_cut_plan([
            {"time_seconds":1.0,"strength":0.5},
            {"time_seconds":2.0,"strength":0.5},
        ])
        self.assertEqual(plan["format"],"update-p5-ai-edit")
        self.assertEqual(plan["metadata"]["cut_count"],2)
        tools=[x["tool"] for x in plan["steps"]]
        self.assertEqual(tools.count("kdenlive_cut_clip"),2)

    def test_load_rhythm_json(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"r.json"
            p.write_text(json.dumps({"audio":{"beats":[{"time_seconds":1,"strength":0.5}]}}),encoding="utf-8")
            got=mod.load_beats(p)
            self.assertEqual(got[0]["time_seconds"],1.0)


if __name__=="__main__":
    unittest.main()

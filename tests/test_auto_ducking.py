import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "auto_ducking" / "auto_ducking.py"
spec = importlib.util.spec_from_file_location("auto_ducking", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class AutoDuckingTests(unittest.TestCase):
    def test_merge_speech_ranges(self):
        segs = [
            {"start_seconds": 1.0, "end_seconds": 2.0},
            {"start_seconds": 2.05, "end_seconds": 3.0},
            {"start_seconds": 5.0, "end_seconds": 6.0},
        ]
        got = mod.merge_speech_ranges(segs, lead=0.1, tail=0.1, merge_gap=0.2)
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0]["start_seconds"], 0.9)
        self.assertAlmostEqual(got[0]["end_seconds"], 3.1)

    def test_plan_uses_cut_and_volume(self):
        ranges = [
            {"start_seconds": 1.0, "end_seconds": 2.0},
            {"start_seconds": 4.0, "end_seconds": 5.0},
        ]
        plan = mod.build_ducking_plan(ranges, duck_gain_db=-12.0)
        tools = [s["tool"] for s in plan["steps"]]
        self.assertEqual(tools.count("kdenlive_cut_clip"), 4)
        self.assertEqual(tools.count("kdenlive_set_clip_volume"), 2)
        self.assertEqual(plan["format"], "update-p5-ai-edit")

    def test_loader_accepts_segments_object(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.json"
            p.write_text(json.dumps({"segments":[{"start":0,"end":1,"text":"hi"}]}), encoding="utf-8")
            got = mod._load_segments(p)
            self.assertEqual(got, [{"start_seconds":0.0,"end_seconds":1.0}])


if __name__ == "__main__":
    unittest.main()

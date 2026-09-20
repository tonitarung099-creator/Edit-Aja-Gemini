import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "media_intelligence" / "media_intelligence.py"
spec = importlib.util.spec_from_file_location("media_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class MediaIntelligenceTests(unittest.TestCase):
    def test_parse_silence(self):
        text = """
[silencedetect @ a] silence_start: 1.25
[silencedetect @ a] silence_end: 3.75 | silence_duration: 2.5
[silencedetect @ a] silence_start: 8
"""
        got = mod.parse_silencedetect(text, duration=10.0)
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0]["start_seconds"], 1.25)
        self.assertAlmostEqual(got[0]["end_seconds"], 3.75)
        self.assertAlmostEqual(got[1]["end_seconds"], 10.0)

    def test_parse_scenes(self):
        text = """
[Parsed_showinfo_1 @ x] n:1 pts:123 pts_time:2.500 pos:123
[Parsed_showinfo_1 @ x] n:2 pts:456 pts_time:7.250 pos:456
"""
        self.assertEqual(mod.parse_scene_times(text), [2.5, 7.25])

    def test_parse_black(self):
        text = "[blackdetect @ x] black_start:4.1 black_end:5.6 black_duration:1.5"
        got = mod.parse_blackdetect(text)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0]["duration_seconds"], 1.5)

    def test_pacing(self):
        got = mod.pacing_summary([2.0, 5.0, 9.0], 12.0)
        self.assertEqual(got["scene_count"], 4)
        self.assertAlmostEqual(got["average_scene_seconds"], 3.0)

    def test_smart_cut_edges_and_merge(self):
        silence = [
            {"start_seconds": 1.0, "end_seconds": 3.0},
            {"start_seconds": 3.02, "end_seconds": 5.0},
            {"start_seconds": 9.2, "end_seconds": 10.0},
        ]
        got = mod.smart_cut_ranges(
            silence,
            duration=10.0,
            edge_keep=0.1,
            min_remove=0.3,
            keep_start=0.0,
            keep_end=0.2,
            merge_gap=0.25,
        )
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[0]["start_seconds"], 1.1)
        self.assertAlmostEqual(got[0]["end_seconds"], 4.9)
        self.assertAlmostEqual(got[1]["end_seconds"], 9.8)

    def test_build_plan_is_phase6_compatible(self):
        ranges = [{"start_seconds": 2.0, "end_seconds": 3.0, "duration_seconds": 1.0}]
        plan = mod.build_smart_cut_plan(Path("video.mp4"), ranges)
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        self.assertEqual(plan["version"], 1)
        step = plan["steps"][0]
        self.assertEqual(step["tool"], "kdenlive_remove_ranges")
        self.assertEqual(len(step["arguments"]["track_ids"]), 2)


if __name__ == "__main__":
    unittest.main()

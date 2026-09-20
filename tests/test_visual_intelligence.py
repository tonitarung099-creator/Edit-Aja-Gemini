import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "visual_intelligence" / "visual_intelligence.py"
spec = importlib.util.spec_from_file_location("visual_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class VisualIntelligenceTests(unittest.TestCase):
    def test_smoothing(self):
        src = [
            {"time_seconds": 0.0, "x": 0.2, "y": 0.5, "confidence": 1.0},
            {"time_seconds": 1.0, "x": 0.8, "y": 0.5, "confidence": 1.0},
        ]
        got = mod.smooth_track(src, 0.5)
        self.assertAlmostEqual(got[1]["x"], 0.5)

    def test_transform_clamps_canvas(self):
        got = mod.transform_for_focus(
            0.0, 0.5, project_width=1080, project_height=1920, scale_percent=180, safe_margin=0.0
        )
        self.assertLessEqual(got["x"], 0.0)
        self.assertGreaterEqual(got["x"], 1080 - 1080 * 1.8)

    def test_simplify(self):
        src = [
            {"time_seconds": 0.0, "x": 0.5, "y": 0.5, "confidence": 1.0},
            {"time_seconds": 0.2, "x": 0.51, "y": 0.5, "confidence": 1.0},
            {"time_seconds": 1.0, "x": 0.8, "y": 0.5, "confidence": 1.0},
        ]
        got = mod.simplify_track(src, min_interval=0.8, movement_threshold=0.1)
        self.assertEqual(len(got), 2)

    def test_plan_uses_cut_and_transform(self):
        src = [
            {"time_seconds": 0.0, "x": 0.4, "y": 0.5, "confidence": 1.0},
            {"time_seconds": 1.5, "x": 0.7, "y": 0.5, "confidence": 1.0},
        ]
        plan = mod.build_reframe_plan(
            src,
            project_width=1080,
            project_height=1920,
            scale_percent=180,
            min_interval=0.5,
            movement_threshold=0.05,
        )
        tools = [s["tool"] for s in plan["steps"]]
        self.assertIn("kdenlive_cut_clip", tools)
        self.assertIn("kdenlive_set_transform", tools)
        self.assertEqual(plan["format"], "update-p5-ai-edit")

    def test_load_track_aliases(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "track.json"
            p.write_text(json.dumps({"points": [{"time": 1, "x": 0.2, "y": 0.3}]}), encoding="utf-8")
            got = mod.load_track(p)
            self.assertEqual(len(got), 1)
            self.assertAlmostEqual(got[0]["time_seconds"], 1.0)


if __name__ == "__main__":
    unittest.main()

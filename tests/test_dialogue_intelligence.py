import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "dialogue_intelligence" / "dialogue_intelligence.py"
spec = importlib.util.spec_from_file_location("dialogue_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class DialogueIntelligenceTests(unittest.TestCase):
    def test_detect_fillers_repeats_and_gaps(self):
        words = [
            {"start_seconds": 0.0, "end_seconds": 0.2, "text": "eee"},
            {"start_seconds": 0.3, "end_seconds": 0.6, "text": "saya"},
            {"start_seconds": 0.7, "end_seconds": 0.9, "text": "saya"},
            {"start_seconds": 2.2, "end_seconds": 2.5, "text": "lanjut"},
        ]
        got = mod.analyze_words(words, repeat_gap=0.5, long_gap=1.0)
        self.assertEqual(got["summary"]["filler_count"], 1)
        self.assertEqual(got["summary"]["repeat_count"], 1)
        self.assertEqual(got["summary"]["long_gap_count"], 1)

    def test_cut_ranges(self):
        analysis = {
            "filler_words": [{"start_seconds": 1.0, "end_seconds": 1.2}],
            "repeated_words": [{"start_seconds": 1.21, "end_seconds": 1.4}],
            "long_gaps": [],
        }
        got = mod.build_cut_ranges(analysis, padding=0.01)
        self.assertEqual(len(got), 1)
        self.assertLess(got[0]["start_seconds"], 1.0)
        self.assertGreater(got[0]["end_seconds"], 1.4)

    def test_ai_edit_plan(self):
        plan = mod.to_ai_edit([{"start_seconds": 1.0, "end_seconds": 1.5}])
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        self.assertEqual(plan["steps"][0]["tool"], "kdenlive_remove_ranges")
        self.assertEqual(len(plan["steps"][0]["arguments"]["track_ids"]), 2)

    def test_load_words(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "transcript.json"
            path.write_text(
                json.dumps({"words": [{"start_seconds": 0, "end_seconds": 1, "text": "um"}]}),
                encoding="utf-8",
            )
            got = mod.load_words(path)
            self.assertEqual(got[0]["text"], "um")


if __name__ == "__main__":
    unittest.main()

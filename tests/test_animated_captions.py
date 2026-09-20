import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "animated_captions" / "animated_captions.py"
spec = importlib.util.spec_from_file_location("animated_captions", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class AnimatedCaptionTests(unittest.TestCase):
    def test_phase_segments_pop(self):
        got=mod.phase_segments(0.0,1.0,"pop")
        self.assertEqual(len(got),3)
        self.assertAlmostEqual(got[-1]["end_seconds"],1.0)
        self.assertEqual(got[1]["scale_percent"],112.0)

    def test_short_word_collapses_animation(self):
        got=mod.phase_segments(0.0,0.05,"bounce",minimum_phase=0.03)
        self.assertEqual(len(got),1)

    def test_build_plan(self):
        words=[
            {"start_seconds":0.0,"end_seconds":0.5,"text":"hello"},
            {"start_seconds":0.5,"end_seconds":1.0,"text":"world"},
        ]
        plan=mod.build_plan(words,preset="punch")
        self.assertEqual(plan["format"],"update-p5-ai-edit")
        self.assertEqual(plan["metadata"]["word_count"],2)
        tools=[x["tool"] for x in plan["steps"]]
        self.assertIn("kdenlive_create_title",tools)
        self.assertIn("kdenlive_set_transform",tools)

    def test_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.json"
            p.write_text(json.dumps({"words":[{"start_seconds":0,"end_seconds":1,"text":" hi "}]}),encoding="utf-8")
            got=mod.load_words(p)
            self.assertEqual(got[0]["text"],"hi")


if __name__=="__main__":
    unittest.main()

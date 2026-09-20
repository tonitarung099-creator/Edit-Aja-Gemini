import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "audio_intelligence" / "audio_intelligence.py"
spec = importlib.util.spec_from_file_location("audio_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class AudioIntelligenceTests(unittest.TestCase):
    def test_parse_loudness(self):
        text = """
{
  "input_i" : "-21.40",
  "input_tp" : "-3.00",
  "input_lra" : "4.10",
  "input_thresh" : "-31.00",
  "output_i" : "-16.00"
}
"""
        got = mod.parse_loudness(text)
        self.assertAlmostEqual(got["input_i"], -21.4)
        self.assertAlmostEqual(got["input_tp"], -3.0)

    def test_gain_hits_target_without_peak_violation(self):
        got = mod.recommend_gain({"input_i": -20.0, "input_tp": -6.0}, target_lufs=-16.0, true_peak_limit=-1.5)
        self.assertAlmostEqual(got["recommended_gain_db"], 4.0)

    def test_gain_limited_by_true_peak(self):
        got = mod.recommend_gain({"input_i": -24.0, "input_tp": -2.0}, target_lufs=-16.0, true_peak_limit=-1.5)
        self.assertAlmostEqual(got["recommended_gain_db"], 0.5)

    def test_gain_limited_by_max_cut(self):
        got = mod.recommend_gain({"input_i": -2.0, "input_tp": -1.0}, target_lufs=-16.0, max_cut_db=8.0)
        self.assertAlmostEqual(got["recommended_gain_db"], -8.0)
        self.assertTrue(got["limited_by_safety_bounds"])

    def test_plan_uses_native_audio_tools(self):
        rec = {"recommended_gain_db": 3.25}
        plan = mod.build_plan(Path("voice.wav"), rec, fade_in=0.2, fade_out=0.3)
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        self.assertEqual(plan["steps"][0]["tool"], "kdenlive_set_clip_volume")
        self.assertEqual(plan["steps"][1]["tool"], "kdenlive_set_audio_fade")
        self.assertEqual(plan["steps"][0]["arguments"]["clip_id"]["$clip_at"]["track"]["audio"], True)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from array import array
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "rhythm_intelligence" / "rhythm_intelligence.py"
spec = importlib.util.spec_from_file_location("rhythm_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class RhythmIntelligenceTests(unittest.TestCase):
    def test_activity_ranges(self):
        samples = [
            {"time_seconds": 0.25, "motion_score": 0.01},
            {"time_seconds": 0.50, "motion_score": 0.08},
            {"time_seconds": 0.75, "motion_score": 0.09},
            {"time_seconds": 1.00, "motion_score": 0.01},
            {"time_seconds": 2.00, "motion_score": 0.10},
            {"time_seconds": 2.25, "motion_score": 0.11},
            {"time_seconds": 2.50, "motion_score": 0.12},
        ]
        got = mod.activity_ranges(samples, threshold=0.05, minimum_duration=0.4, bridge_gap=0.05)
        self.assertEqual(len(got), 2)
        self.assertGreater(got[0]["average_motion"], 0.05)

    def test_energy_envelope(self):
        samples = array("h", [0] * 1000 + [10000] * 1000)
        env = mod.energy_envelope(samples, sample_rate=1000, window_ms=100, hop_ms=50)
        self.assertTrue(env)
        self.assertGreater(env[-1]["rms"], env[0]["rms"])

    def test_detect_beats(self):
        env = []
        for i in range(30):
            rms = 0.02
            if i in {5, 15, 25}:
                rms = 0.8
            env.append({"time_seconds": i * 0.1, "rms": rms})
        beats = mod.detect_beats(env, sensitivity=0.5, min_interval=0.5)
        self.assertGreaterEqual(len(beats), 2)
        self.assertIsNotNone(beats[0]["estimated_bpm"])


if __name__ == "__main__":
    unittest.main()

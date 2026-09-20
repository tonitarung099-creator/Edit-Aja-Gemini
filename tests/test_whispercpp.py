import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "speech_backends" / "whispercpp.py"
spec = importlib.util.spec_from_file_location("whispercpp", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class WhisperCppAdapterTests(unittest.TestCase):
    def test_normalize_segments_and_tokens(self):
        raw = {
            "params": {"language": "auto"},
            "result": {"language": "id"},
            "transcription": [
                {
                    "timestamps": {"from": "00:00:00,000", "to": "00:00:01,500"},
                    "offsets": {"from": 0, "to": 1500},
                    "text": " Halo dunia",
                    "tokens": [
                        {"text": " Halo", "offsets": {"from": 0, "to": 600}, "p": 0.9},
                        {"text": " dunia", "offsets": {"from": 600, "to": 1500}, "p": 0.8},
                    ],
                }
            ],
        }
        got = mod.normalize_whisper_json(raw)
        self.assertEqual(got["language"], "id")
        self.assertEqual(len(got["segments"]), 1)
        self.assertEqual(len(got["words"]), 2)
        self.assertAlmostEqual(got["segments"][0]["end_seconds"], 1.5)

    def test_ai_edit_conversion(self):
        transcript = {
            "language": "id",
            "segments": [{"start_seconds": 0.0, "end_seconds": 1.0, "text": "Halo"}],
        }
        plan = mod.transcript_to_ai_edit(transcript)
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        self.assertEqual(plan["steps"][0]["tool"], "kdenlive_add_subtitle_batch")
        self.assertEqual(plan["steps"][0]["arguments"]["segments"][0]["text"], "Halo")


if __name__ == "__main__":
    unittest.main()

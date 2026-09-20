import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "caption_intelligence" / "caption_intelligence.py"
spec = importlib.util.spec_from_file_location("caption_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class CaptionIntelligenceTests(unittest.TestCase):
    def test_srt_parse(self):
        text = """1
00:00:01,000 --> 00:00:03,500
Hello world.

2
00:00:04,000 --> 00:00:05,000
Second line
"""
        got = mod.parse_srt(text)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["text"], "Hello world.")
        self.assertAlmostEqual(got[0]["end_seconds"], 3.5)

    def test_phrase_resegment(self):
        src = [{"start_seconds": 0.0, "end_seconds": 4.0, "text": "one two three four five six seven eight"}]
        got = mod.resegment(src, mode="phrase", max_words=4, max_chars=30, max_duration=3.0)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["text"], "one two three four")
        self.assertAlmostEqual(got[-1]["end_seconds"], 4.0)

    def test_word_mode(self):
        src = [{"start_seconds": 0.0, "end_seconds": 2.0, "text": "hello world"}]
        got = mod.resegment(src, mode="word", max_duration=2.0)
        self.assertEqual([x["text"] for x in got], ["hello", "world"])
        self.assertAlmostEqual(got[-1]["end_seconds"], 2.0)

    def test_ai_edit_output(self):
        segs = [{"start_seconds": 1.0, "end_seconds": 2.0, "text": "Caption"}]
        doc = mod.to_ai_edit(segs, title="T", style="Default", layer=0)
        self.assertEqual(doc["format"], "update-p5-ai-edit")
        self.assertEqual(doc["steps"][0]["tool"], "kdenlive_add_subtitle_batch")
        self.assertEqual(doc["steps"][0]["arguments"]["segments"][0]["text"], "Caption")

    def test_json_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "transcript.json"
            p.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "Hi"}]}), encoding="utf-8")
            got = mod.load_segments(p)
            self.assertEqual(got[0]["text"], "Hi")


if __name__ == "__main__":
    unittest.main()

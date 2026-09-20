import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "bad_take_review" / "bad_take_review.py"
spec = importlib.util.spec_from_file_location("bad_take_review", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class BadTakeReviewTests(unittest.TestCase):
    def test_correction_language_candidate(self):
        segs=[
            {"source_index":0,"start_seconds":0.0,"end_seconds":1.0,"text":"Maksud saya bukan itu","speaker":None},
            {"source_index":1,"start_seconds":1.2,"end_seconds":2.5,"text":"Maksud saya bagian ini","speaker":None},
        ]
        report=mod.review(segs)
        self.assertGreaterEqual(report["summary"]["candidate_count"],1)
        self.assertIn("correction_language",report["candidates"][0]["reasons"])

    def test_restart_prefix(self):
        segs=[
            {"source_index":0,"start_seconds":0.0,"end_seconds":0.8,"text":"Jepang menjadi negara","speaker":None},
            {"source_index":1,"start_seconds":1.0,"end_seconds":3.0,"text":"Jepang menjadi negara modern dengan cepat","speaker":None},
        ]
        report=mod.review(segs,prefix_words=3)
        self.assertTrue(any("restarted_phrase" in r for r in report["candidates"][0]["reasons"]))

    def test_approved_only_compiles(self):
        report={
            "format":"update-p5-bad-take-review","version":1,
            "candidates":[
                {"id":"candidate-0001","start_seconds":1.0,"end_seconds":2.0},
                {"id":"candidate-0002","start_seconds":3.0,"end_seconds":4.0},
            ]
        }
        plan=mod.to_ai_edit(report,{"candidate-0002"})
        ranges=plan["steps"][0]["arguments"]["ranges"]
        self.assertEqual(len(ranges),1)
        self.assertGreater(ranges[0]["start_seconds"],2.9)
        self.assertEqual(plan["format"],"update-p5-ai-edit")

    def test_loader(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"t.json"
            p.write_text(json.dumps({"segments":[{"start":0,"end":1,"text":"ulang lagi"}]}),encoding="utf-8")
            got=mod.load_segments(p)
            self.assertEqual(got[0]["text"],"ulang lagi")


if __name__=="__main__":
    unittest.main()

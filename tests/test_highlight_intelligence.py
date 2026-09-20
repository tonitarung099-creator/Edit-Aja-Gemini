import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "highlight_intelligence" / "highlight_intelligence.py"
spec = importlib.util.spec_from_file_location("highlight_intelligence", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class HighlightIntelligenceTests(unittest.TestCase):
    def test_text_score_hooks(self):
        score,reasons=mod.text_score("Ternyata jawabannya berbeda. Mengapa?",30.0)
        self.assertGreater(score,1.5)
        self.assertIn("hook_language",reasons)
        self.assertIn("question",reasons)

    def test_candidates_non_overlapping(self):
        segs=[]
        t=0.0
        for i in range(12):
            segs.append({
                "source_index":i,
                "start_seconds":t,
                "end_seconds":t+5.0,
                "text":("Ternyata ini fakta penting " if i%3==0 else "Penjelasan berlanjut ") + str(i),
            })
            t+=5.0
        report=mod.candidates(segs,min_duration=15,target_duration=20,max_duration=30,max_candidates=3)
        self.assertEqual(report["format"],"update-p5-highlight-review")
        self.assertGreaterEqual(report["summary"]["candidate_count"],1)
        self.assertLessEqual(report["summary"]["candidate_count"],3)

    def test_compile_highlight_removes_outside(self):
        report={
            "format":"update-p5-highlight-review",
            "summary":{"transcript_end_seconds":100},
            "candidates":[{"id":"highlight-001","start_seconds":20,"end_seconds":50}]
        }
        plan=mod.to_ai_edit(report,"highlight-001",padding=0)
        ranges=plan["steps"][0]["arguments"]["ranges"]
        self.assertEqual(ranges,[{"start_seconds":0.0,"end_seconds":20.0},{"start_seconds":50.0,"end_seconds":100.0}])
        self.assertEqual(plan["format"],"update-p5-ai-edit")


if __name__=="__main__":
    unittest.main()

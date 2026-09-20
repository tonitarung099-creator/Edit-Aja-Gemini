import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "segmentation_backends" / "sam2_video.py"
spec = importlib.util.spec_from_file_location("sam2_video", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class Sam2AdapterTests(unittest.TestCase):
    def test_load_point_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "prompt.json"
            p.write_text(json.dumps({"objects":[{"id":"p","frame_idx":0,"points":[[100,200]],"labels":[1]}]}), encoding="utf-8")
            got = mod.load_prompts(p)
            self.assertEqual(got[0]["id"], "p")
            self.assertEqual(got[0]["points"], [[100.0, 200.0]])

    def test_load_box_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "prompt.json"
            p.write_text(json.dumps({"objects":[{"id":"car","box":[10,20,100,200]}]}), encoding="utf-8")
            got = mod.load_prompts(p)
            self.assertEqual(got[0]["box"], [10.0,20.0,100.0,200.0])

    def test_subject_track_from_mask_track(self):
        mask_track = {
            "objects":[{
                "id":"person",
                "frames":[
                    {"time_seconds":0.0,"centroid_normalized":[0.4,0.5],"area_ratio":0.1},
                    {"time_seconds":1.0,"centroid_normalized":[0.6,0.5],"area_ratio":0.2}
                ]
            }]
        }
        got = mod.subject_track(mask_track, "person")
        self.assertEqual(got["format"], "update-p5-subject-track")
        self.assertEqual(len(got["samples"]), 2)
        self.assertAlmostEqual(got["samples"][1]["x"], 0.6)

    def test_cutout_plan(self):
        plan = mod.cutout_plan(Path("subject.mov"), at=3.0)
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        tools = [x["tool"] for x in plan["steps"]]
        self.assertIn("kdenlive_import_media", tools)
        self.assertIn("kdenlive_insert_bin_clip", tools)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "workflow_presets" / "workflow_presets.py"
spec = importlib.util.spec_from_file_location("workflow_presets", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class WorkflowPresetTests(unittest.TestCase):
    def test_documentary_with_rhythm(self):
        cfg=mod.make_preset("documentary",transcript="t.json",rhythm="r.json")
        ids=[x["id"] for x in cfg["stages"]]
        self.assertIn("captions",ids)
        self.assertIn("broll",ids)
        self.assertIn("beat-cuts",ids)

    def test_shorts_with_subject_track(self):
        cfg=mod.make_preset("shorts",transcript="t.json",subject_track="s.json")
        ids=[x["id"] for x in cfg["stages"]]
        self.assertIn("animated-captions",ids)
        self.assertIn("vertical-reframe",ids)
        self.assertEqual(cfg["variables"]["SUBJECT_TRACK"],"s.json")

    def test_podcast_has_speaker_captions(self):
        cfg=mod.make_preset("podcast",transcript="t.json")
        self.assertEqual(cfg["stages"][0]["id"],"speaker-captions")

    def test_talking_head_has_reviews(self):
        cfg=mod.make_preset("talking-head",transcript="t.json")
        ids=[x["id"] for x in cfg["stages"]]
        self.assertIn("bad-takes",ids)
        self.assertIn("highlights",ids)


if __name__=="__main__":
    unittest.main()

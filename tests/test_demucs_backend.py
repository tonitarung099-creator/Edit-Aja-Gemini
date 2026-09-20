import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "audio_backends" / "demucs.py"
spec = importlib.util.spec_from_file_location("demucs_backend", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class DemucsBackendTests(unittest.TestCase):
    def test_discover_stems(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=Path("song.mp3")
            out=root/"htdemucs"/"song"
            out.mkdir(parents=True)
            (out/"vocals.wav").write_bytes(b"x")
            (out/"no_vocals.wav").write_bytes(b"x")
            stems=mod.discover_stems(root,src)
            self.assertIn("vocals",stems)
            self.assertIn("no_vocals",stems)

    def test_stable_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=root/"vocals.wav"; src.write_bytes(b"x")
            dest=root/"stable"
            copied=mod.stable_copy({"vocals":src},dest,Path("song.mp3"))
            self.assertTrue(copied["vocals"].exists())
            self.assertEqual(copied["vocals"].name,"song-vocals.wav")

    def test_plan_imports_stems(self):
        stems={"vocals":Path("song-vocals.wav"),"no_vocals":Path("song-no_vocals.wav")}
        plan=mod.build_plan(stems,mute_original=True)
        self.assertEqual(plan["format"],"update-p5-ai-edit")
        tools=[x["tool"] for x in plan["steps"]]
        self.assertEqual(tools.count("kdenlive_add_track"),2)
        self.assertEqual(tools.count("kdenlive_import_media"),2)
        self.assertIn("kdenlive_set_clip_volume",tools)


if __name__=="__main__":
    unittest.main()

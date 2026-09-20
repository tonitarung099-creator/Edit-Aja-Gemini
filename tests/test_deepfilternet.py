import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "audio_backends" / "deepfilternet.py"
spec = importlib.util.spec_from_file_location("deepfilternet", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class DeepFilterNetAdapterTests(unittest.TestCase):
    def test_find_enhanced_wav_prefers_largest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "input.wav"
            inp.write_bytes(b"x")
            out = root / "out"
            out.mkdir()
            a = out / "a.wav"
            b = out / "b.wav"
            a.write_bytes(b"a" * 10)
            b.write_bytes(b"b" * 20)
            self.assertEqual(mod.find_enhanced_wav(out, inp), b)

    def test_plan_imports_clean_audio_and_mutes_original(self):
        plan = mod.build_replace_audio_plan(Path("clean.wav"), at=2.0, mute_original=True)
        tools = [s["tool"] for s in plan["steps"]]
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        self.assertIn("kdenlive_import_media", tools)
        self.assertIn("kdenlive_insert_bin_clip", tools)
        self.assertIn("kdenlive_set_clip_volume", tools)

    def test_plan_can_keep_original(self):
        plan = mod.build_replace_audio_plan(Path("clean.wav"), mute_original=False)
        tools = [s["tool"] for s in plan["steps"]]
        self.assertNotIn("kdenlive_set_clip_volume", tools)


if __name__ == "__main__":
    unittest.main()

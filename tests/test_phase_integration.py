import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


ai_edit = load("update_p5_ai_edit", ROOT / "tools" / "ai_edit" / "update_p5_ai_edit.py")
media = load("media_intelligence", ROOT / "tools" / "media_intelligence" / "media_intelligence.py")
captions = load("caption_intelligence", ROOT / "tools" / "caption_intelligence" / "caption_intelligence.py")
audio = load("audio_intelligence", ROOT / "tools" / "audio_intelligence" / "audio_intelligence.py")


class CrossPhaseAiEditContractTests(unittest.TestCase):
    def assert_valid_ai_edit(self, plan):
        self.assertEqual(plan["format"], ai_edit.FORMAT)
        self.assertEqual(plan["version"], ai_edit.VERSION)
        self.assertEqual(ai_edit.validate_plan(plan), [])

    def test_media_smart_cut_emits_phase6_contract(self):
        plan = media.build_smart_cut_plan(
            Path("input.mp4"),
            [{"start_seconds": 2.0, "end_seconds": 3.2, "duration_seconds": 1.2}],
            video_track_index=0,
            audio_track_index=0,
        )
        self.assert_valid_ai_edit(plan)
        tools = [step["tool"] for step in plan["steps"]]
        self.assertIn("kdenlive_remove_ranges", tools)
        self.assertIn("kdenlive_save_project", tools)

    def test_caption_intelligence_emits_phase6_contract(self):
        plan = captions.to_ai_edit(
            [
                {"start_seconds": 0.0, "end_seconds": 1.0, "text": "Hello"},
                {"start_seconds": 1.0, "end_seconds": 2.0, "text": "world"},
            ],
            title="Contract test",
            style="Default",
            layer=0,
        )
        self.assert_valid_ai_edit(plan)
        self.assertEqual(plan["steps"][0]["tool"], "kdenlive_add_subtitle_batch")

    def test_audio_intelligence_emits_phase6_contract(self):
        plan = audio.build_plan(
            Path("voice.mp4"),
            {"recommended_gain_db": -2.25},
            clip_time=0.1,
            audio_track_index=0,
            fade_in=0.15,
            fade_out=0.25,
        )
        self.assert_valid_ai_edit(plan)
        tools = [step["tool"] for step in plan["steps"]]
        self.assertIn("kdenlive_set_clip_volume", tools)
        self.assertIn("kdenlive_set_audio_fade", tools)
        self.assertIn("kdenlive_save_project", tools)


if __name__ == "__main__":
    unittest.main()

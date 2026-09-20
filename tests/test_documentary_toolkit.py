import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "documentary_toolkit" / "documentary_toolkit.py"
spec = importlib.util.spec_from_file_location("documentary_toolkit", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class DocumentaryToolkitTests(unittest.TestCase):
    def test_lower_third_uses_native_title(self):
        steps = mod.lower_third_steps(prefix="lt", name="Toni", role="Narrator", at=2.0, duration=4.0)
        self.assertEqual(steps[0]["tool"], "kdenlive_add_track")
        self.assertEqual(steps[1]["tool"], "kdenlive_create_title")
        self.assertIn("Toni", steps[1]["arguments"]["text"])

    def test_broll_import_insert_resize(self):
        steps = mod.broll_steps(prefix="b", asset="shot.mp4", at=10.0, duration=3.0)
        tools = [s["tool"] for s in steps]
        self.assertEqual(
            tools[:4],
            ["kdenlive_add_track", "kdenlive_import_media", "kdenlive_insert_bin_clip", "kdenlive_resize_item"],
        )

    def test_ken_burns_creates_editable_segments(self):
        steps = mod.ken_burns_steps(prefix="k", asset="photo.jpg", at=0.0, duration=4.0, segments=4)
        tools = [s["tool"] for s in steps]
        self.assertEqual(tools.count("kdenlive_cut_clip"), 3)
        self.assertGreaterEqual(tools.count("kdenlive_set_transform"), 4)

    def test_compile_mixed_documentary_config(self):
        config = {
            "title": "Doc",
            "operations": [
                {"type": "chapter_card", "title": "Chapter", "subtitle": "", "at": 0.0, "duration": 2.0},
                {"type": "broll_placeholder", "label": "Archive photo", "at": 5.0, "duration": 3.0},
                {"type": "lower_third", "name": "Person", "role": "Role", "at": 10.0, "duration": 3.0},
            ],
        }
        plan = mod.compile_config(config)
        self.assertEqual(plan["format"], "update-p5-ai-edit")
        self.assertEqual(plan["metadata"]["operation_count"], 3)
        self.assertEqual(plan["steps"][-1]["tool"], "kdenlive_save_project")


if __name__ == "__main__":
    unittest.main()

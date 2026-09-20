import unittest

from tools.local_edit_agent.local_edit_agent import compute_zoom_keyframes, interpret


class LocalEditAgentTests(unittest.TestCase):
    def test_typo_split_bare_number_defaults_to_minutes(self):
        result = interpret("ptong 5")
        self.assertEqual(result["route"], "local")
        self.assertEqual(result["intent"], "split")
        self.assertEqual(result["parameters"]["time_seconds"], 300.0)
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(result["normalized_text"], "potong 5")

    def test_explicit_split_minute(self):
        result = interpret("potong menit 5")
        self.assertEqual(result["intent"], "split")
        self.assertEqual(result["parameters"]["time_seconds"], 300.0)
        self.assertFalse(result["needs_confirmation"])

    def test_scene_typo_delete(self):
        result = interpret("hpus sceen 73", context={"scenes": {"73": {"start": 501.4, "end": 507.9}}})
        self.assertEqual(result["intent"], "delete_scene")
        self.assertEqual(result["parameters"]["scene_start"], 73)
        self.assertEqual(result["parameters"]["resolved_ranges"][0]["start"], 501.4)

    def test_zoom_math_4_5_seconds(self):
        zoom = compute_zoom_keyframes(100, 111, 5, 4.5, "smooth")
        self.assertAlmostEqual(zoom["end_scale_percent"], 109.9)
        self.assertFalse(zoom["reaches_target"])

    def test_zoom_math_long_clip_holds(self):
        zoom = compute_zoom_keyframes(100, 111, 5, 8, "smooth")
        self.assertEqual(zoom["end_scale_percent"], 111)
        self.assertTrue(zoom["hold_after_target"])
        self.assertEqual(zoom["keyframes"][-1]["time"], 8)
        self.assertEqual(zoom["keyframes"][-1]["scale_percent"], 111)

    def test_typo_all_snapshot_zoom(self):
        result = interpret(
            "semua snapshpt zom 100 ke 111 5 dtk",
            context={"snapshots": [{"id": "a", "duration": 4.5}, {"id": "b", "duration": 8.0}]},
        )
        self.assertEqual(result["route"], "local")
        self.assertEqual(result["intent"], "animate_scale")
        self.assertEqual(len(result["parameters"]["animations"]), 2)
        self.assertAlmostEqual(result["parameters"]["animations"][0]["end_scale_percent"], 109.9)
        self.assertEqual(result["parameters"]["animations"][1]["end_scale_percent"], 111)

    def test_zoom_routes_to_native_transform_keyframes(self):
        result = interpret(
            "snapshot zoom 100 ke 111 5 dtk",
            context={"selected_clip_id": 44, "selected_clip_duration": 4.5},
        )
        self.assertEqual(result["native_tool_hint"], "kdenlive_set_transform_keyframes")
        self.assertAlmostEqual(result["parameters"]["animations"][0]["end_scale_percent"], 109.9)

    def test_specialized_local_tool_route(self):
        self.assertEqual(interpret("transkrip video ini lalu buat subtitle")["route"], "local_tool")

    def test_semantic_request_routes_to_ai(self):
        self.assertEqual(interpret("pilih bagian terbaik berdasarkan isi cerita")["route"], "ai")

    def test_external_asset_search_routes_to_mcp(self):
        self.assertEqual(interpret("cari gambar online tentang tokyo")["route"], "mcp")


if __name__ == "__main__":
    unittest.main()

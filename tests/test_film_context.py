import importlib.util
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "film_context" / "film_context.py"
spec = importlib.util.spec_from_file_location("film_context", MODULE_PATH)
fc = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = fc
spec.loader.exec_module(fc)


SRT = """1
00:00:00,500 --> 00:00:02,500
John masuk ke rumah.

2
00:00:04,000 --> 00:00:06,000
Di mana ayahku?

3
00:00:07,500 --> 00:00:09,500
Ayahmu sudah pergi.
"""


class FilmContextTests(unittest.TestCase):
    def test_parse_srt(self):
        subtitles = fc.parse_srt(SRT)
        self.assertEqual(len(subtitles), 3)
        self.assertAlmostEqual(subtitles[0].start, 0.5)
        self.assertEqual(subtitles[1].text, "Di mana ayahku?")

    def test_scene_segments(self):
        scenes = fc.scene_segments([3.0, 7.0], 10.0)
        self.assertEqual([x["scene_id"] for x in scenes], [1, 2, 3])
        self.assertEqual(scenes[1]["start_seconds"], 3.0)
        self.assertEqual(scenes[2]["end_seconds"], 10.0)

    def test_dialogue_assignment_by_overlap(self):
        scenes = fc.scene_segments([3.0, 7.0], 10.0)
        subtitles = fc.parse_srt(SRT)
        text, count = fc.scene_dialogue(scenes[1], subtitles)
        self.assertEqual(count, 1)
        self.assertIn("ayahku", text)

    def _index(self, root: Path):
        media = root / "movie.mp4"
        media.write_bytes(b"fake media for deterministic unit test")
        scenes = fc.scene_segments([3.0, 7.0], 10.0)
        subtitles = fc.parse_srt(SRT)
        fc.write_index(
            root / "index",
            media=media,
            duration=10.0,
            threshold=0.35,
            scenes=scenes,
            subtitles=subtitles,
            fingerprint="unit-test",
        )
        return root / "index"

    def test_status_is_local_and_small(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._index(Path(tmp))
            value = fc.status(index)
            self.assertTrue(value["ok"])
            self.assertFalse(value["api_required"])
            self.assertEqual(value["scene_count"], 3)

    def test_local_search_ranks_matching_dialogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._index(Path(tmp))
            value = fc.search_index(index, "ayahku", top_k=2)
            self.assertFalse(value["api_used"])
            self.assertEqual(value["results"][0]["scene_id"], 2)
            self.assertGreater(value["results"][0]["score"], 0)

    def test_annotation_becomes_searchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._index(Path(tmp))
            fc.annotate_scene(index, 3, "John mengetahui ayahnya meninggal")
            value = fc.search_index(index, "mengetahui ayahnya meninggal", top_k=1)
            self.assertEqual(value["results"][0]["scene_id"], 3)

    def test_neighbor_context_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._index(Path(tmp))
            value = fc.get_context(index, 2, radius=1)
            self.assertEqual([x["scene_id"] for x in value["scenes"]], [1, 2, 3])
            self.assertTrue(value["scenes"][1]["focus"])

    def test_tool_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._index(Path(tmp))
            result = fc.invoke_tool(index, "movie_search", {"query": "ayahku", "top_k": 1})
            self.assertEqual(result["results"][0]["scene_id"], 2)
            names = [tool["name"] for tool in fc.tool_catalog()["tools"]]
            self.assertIn("movie_get_keyframes", names)
            self.assertIn("movie_get_context", names)

    def test_visual_tags_are_optional_and_searchable_without_openclip(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._index(Path(tmp))
            conn = sqlite3.connect(index / "movie.db")
            try:
                conn.execute(
                    """
                    INSERT INTO scene_visual(scene_id,model,pretrained,frame_time,frame_path,tags_text,tags_json)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        1,
                        "unit-model",
                        "unit-pretrained",
                        1.5,
                        "frame.jpg",
                        "opening a door ; membuka pintu ; inside a house ; dalam rumah",
                        "[]",
                    ),
                )
                conn.commit()
            finally:
                conn.close()

            status = fc.status(index)
            self.assertTrue(status["visual_ready"])
            self.assertEqual(status["visual_scene_count"], 1)

            result = fc.search_index(index, "membuka pintu", top_k=1)
            self.assertEqual(result["results"][0]["scene_id"], 1)
            self.assertIn("membuka pintu", result["results"][0]["visual_tags"])

            scene = fc.get_scene(index, 1)
            self.assertIn("dalam rumah", scene["scene"]["visual_tags"])

    def test_visual_index_command_is_available_without_importing_openclip(self):
        parser = fc.build_parser()
        args = parser.parse_args(["visual-index", "--index-dir", "dummy"])
        self.assertEqual(args.command, "visual-index")

    def test_keyframe_times_avoid_cut_boundaries(self):
        values = [fc._safe_keyframe_time(10.0, 20.0, i, 2) for i in range(2)]
        self.assertGreater(values[0], 10.0)
        self.assertLess(values[-1], 20.0)
        self.assertLess(values[0], values[1])


if __name__ == "__main__":
    unittest.main()

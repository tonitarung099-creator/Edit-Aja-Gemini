import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "documentary_graphics" / "documentary_graphics.py"
spec = importlib.util.spec_from_file_location("documentary_graphics", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class DocumentaryGraphicsTests(unittest.TestCase):
    def test_bar_chart_svg(self):
        svg = mod.bar_chart("Test", [{"label":"A","value":10},{"label":"B","value":5}])
        self.assertIn("<svg", svg)
        self.assertIn("Test", svg)
        self.assertIn("<rect", svg)

    def test_timeline_svg(self):
        svg = mod.timeline_graphic("T", [{"year":1868,"text":"Meiji"},{"year":1945,"text":"Postwar"}])
        self.assertIn("1868", svg)
        self.assertIn("Postwar", svg)

    def test_map_equirectangular_point(self):
        svg = mod.map_overlay("Map", [{"lat":0,"lon":0,"label":"Center"}])
        self.assertIn("Center", svg)
        self.assertIn("<circle", svg)

    def test_compile_writes_assets_and_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = {
                "title":"Doc",
                "graphics":[
                    {"type":"bar_chart","title":"Bars","at":1,"duration":3,"items":[{"label":"A","value":1}]},
                    {"type":"timeline","title":"Timeline","at":5,"duration":4,"events":[{"year":1,"text":"Start"}]}
                ]
            }
            assets, plan = mod.compile_graphics(config, root)
            self.assertEqual(len(assets), 2)
            self.assertTrue(all(p.exists() for p in assets))
            self.assertEqual(plan["format"], "update-p5-ai-edit")
            tools = [s["tool"] for s in plan["steps"]]
            self.assertIn("kdenlive_import_media", tools)
            self.assertIn("kdenlive_resize_item", tools)


if __name__ == "__main__":
    unittest.main()

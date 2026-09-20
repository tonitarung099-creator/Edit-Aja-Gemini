import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "smart_montage" / "smart_montage.py"
spec = importlib.util.spec_from_file_location("smart_montage", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class SmartMontageTests(unittest.TestCase):
    def test_select_boundaries_every_second(self):
        beats=[{"time_seconds":float(i),"strength":1.0} for i in range(1,9)]
        got=mod.select_boundaries(beats,start=0.0,end=8.5,every=2,min_segment=0.2)
        self.assertEqual(got[0],0.0)
        self.assertEqual(got[-1],8.5)
        self.assertIn(1.0,got)
        self.assertIn(3.0,got)

    def test_build_plan_native_ops(self):
        assets=[{"path":"a.jpg"},{"path":"b.jpg"}]
        plan=mod.build_plan(assets,[0.0,2.0,4.0])
        self.assertEqual(plan["format"],"update-p5-ai-edit")
        self.assertEqual(plan["metadata"]["clip_count"],2)
        tools=[x["tool"] for x in plan["steps"]]
        self.assertEqual(tools.count("kdenlive_import_media"),2)
        self.assertEqual(tools.count("kdenlive_insert_bin_clip"),2)
        self.assertEqual(tools.count("kdenlive_resize_item"),2)

    def test_cycle_assets(self):
        assets=[{"path":"a.jpg"}]
        plan=mod.build_plan(assets,[0.0,1.0,2.0,3.0],cycle_assets=True)
        self.assertEqual(plan["metadata"]["clip_count"],3)

    def test_load_config_string_assets(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"c.json"
            p.write_text(json.dumps({"assets":["a.jpg","b.jpg"]}),encoding="utf-8")
            got=mod.load_config(p)
            self.assertEqual(got["assets"][0]["path"],"a.jpg")


if __name__=="__main__":
    unittest.main()

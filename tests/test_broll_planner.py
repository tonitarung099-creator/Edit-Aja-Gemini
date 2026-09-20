import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "broll_planner" / "broll_planner.py"
spec = importlib.util.spec_from_file_location("broll_planner", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class BrollPlannerTests(unittest.TestCase):
    def test_visual_type_year_and_location(self):
        kind,reasons=mod.visual_type("Pada 1868 Jepang memasuki era baru")
        self.assertEqual(kind,"historical_map")
        self.assertIn("year_or_historical_date",reasons)

    def test_visual_type_number(self):
        kind,_=mod.visual_type("Populasi meningkat 25% dalam satu dekade")
        self.assertEqual(kind,"data_graphic")

    def test_plan_spacing(self):
        segs=[
            {"source_index":0,"start_seconds":0.0,"end_seconds":1.0,"text":"Jepang adalah negara kepulauan"},
            {"source_index":1,"start_seconds":1.5,"end_seconds":2.0,"text":"Tokyo menjadi pusat penting"},
            {"source_index":2,"start_seconds":5.0,"end_seconds":6.0,"text":"Pada 1868 Jepang berubah besar"},
        ]
        plan=mod.plan_slots(segs,minimum_gap=2.0,default_duration=2.0,maximum_duration=3.0)
        self.assertEqual(plan["format"],"update-p5-broll-plan")
        self.assertEqual(plan["summary"]["slot_count"],2)

    def test_placeholder_plan(self):
        plan={"slots":[
            {"id":"broll-0001","start_seconds":2.0,"duration_seconds":4.0,"visual_type":"historical_map","narration":"History"}
        ]}
        edit=mod.to_placeholder_ai_edit(plan)
        self.assertEqual(edit["format"],"update-p5-ai-edit")
        tools=[x["tool"] for x in edit["steps"]]
        self.assertIn("kdenlive_create_title",tools)

    def test_asset_plan(self):
        plan={"slots":[
            {"id":"broll-0001","start_seconds":2.0,"duration_seconds":4.0,"visual_type":"illustrative_broll","narration":"Text"}
        ]}
        edit=mod.to_asset_ai_edit(plan,{"broll-0001":"shot.jpg"})
        tools=[x["tool"] for x in edit["steps"]]
        self.assertIn("kdenlive_import_media",tools)
        self.assertIn("kdenlive_resize_item",tools)
        self.assertEqual(edit["metadata"]["inserted_assets"],1)


if __name__=="__main__":
    unittest.main()

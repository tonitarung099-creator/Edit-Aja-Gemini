import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "motion_graphics_templates" / "motion_graphics_templates.py"
spec = importlib.util.spec_from_file_location("motion_graphics_templates", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class MotionGraphicsTemplateTests(unittest.TestCase):
    def test_stat_stages(self):
        item={"type":"stat_reveal","title":"T","value":"99","subtitle":"S","source":"X"}
        stages=mod.stages_for(item)
        self.assertEqual(len(stages),4)
        self.assertIn("99",stages[-1])
        self.assertIn("Source:",stages[-1])

    def test_comparison_stages(self):
        item={"type":"comparison","title":"Compare","left":{"label":"A","value":"1"},"right":{"label":"B","value":"2"}}
        stages=mod.stages_for(item)
        self.assertEqual(len(stages),3)
        self.assertIn("Compare",stages[0])

    def test_compile(self):
        cfg={"templates":[
            {"type":"callout","kicker":"Why","headline":"Big change","body":"Detail","at":1,"duration":3},
            {"type":"progress","title":"P","value":75,"label":"Done","at":5,"duration":4}
        ]}
        with tempfile.TemporaryDirectory() as td:
            assets,plan=mod.compile_templates(cfg,Path(td))
            self.assertTrue(assets)
            self.assertTrue(all(p.exists() for p in assets))
            self.assertEqual(plan["format"],"update-p5-ai-edit")
            tools=[s["tool"] for s in plan["steps"]]
            self.assertIn("kdenlive_import_media",tools)
            self.assertIn("kdenlive_resize_item",tools)


if __name__=="__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "mask_effects" / "mask_effects.py"
spec = importlib.util.spec_from_file_location("mask_effects", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class MaskEffectsTests(unittest.TestCase):
    def test_load_mask_object(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p=root/"mask.json"
            p.write_text(json.dumps({
                "format":"update-p5-mask-track",
                "fps":25,
                "objects":[{"id":"person","frames":[]}]
            }),encoding="utf-8")
            data,obj=mod.load_mask_object(p,"person")
            self.assertEqual(data["fps"],25)
            self.assertEqual(obj["id"],"person")

    def test_normalize_mask_sequence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=root/"src"; dst=root/"dst"
            src.mkdir()
            paths=[]
            for i in range(3):
                p=src/f"m{i}.png"; p.write_bytes(b"fake"); paths.append(p)
            obj={"frames":[
                {"frame_idx":0,"mask_path":str(paths[0])},
                {"frame_idx":1,"mask_path":str(paths[1])},
                {"frame_idx":2,"mask_path":str(paths[2])}
            ]}
            count=mod.normalize_mask_sequence(obj,dst)
            self.assertEqual(count,3)
            self.assertTrue((dst/"000002.png").exists())

    def test_insertion_plan(self):
        plan=mod.insertion_plan(Path("effect.mp4"),at=4.0)
        self.assertEqual(plan["format"],"update-p5-ai-edit")
        tools=[s["tool"] for s in plan["steps"]]
        self.assertEqual(tools[:3],["kdenlive_add_track","kdenlive_import_media","kdenlive_insert_bin_clip"])


if __name__=="__main__":
    unittest.main()

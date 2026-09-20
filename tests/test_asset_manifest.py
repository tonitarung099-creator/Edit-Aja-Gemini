import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "asset_manifest" / "asset_manifest.py"
spec = importlib.util.spec_from_file_location("asset_manifest", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class AssetManifestTests(unittest.TestCase):
    def test_make_manifest(self):
        plan={"slots":[
            {"id":"broll-0001","visual_type":"historical_map","prompt_hint":"Map of Japan","start_seconds":2,"duration_seconds":4}
        ]}
        manifest=mod.make_manifest(plan,style_prefix="Style",negative_suffix="No text")
        self.assertEqual(manifest["format"],"update-p5-ai-asset-manifest")
        item=manifest["items"][0]
        self.assertEqual(item["output_filename"],"broll-0001-historical_map.png")
        self.assertIn("Map of Japan",item["prompt"])

    def test_resolve_exact_name(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"broll-0001-historical_map.png").write_bytes(b"x")
            manifest={"items":[{"slot_id":"broll-0001","output_filename":"broll-0001-historical_map.png"}]}
            mapping,report=mod.resolve_folder(manifest,root)
            self.assertIn("broll-0001",mapping)
            self.assertEqual(report["summary"]["missing"],0)

    def test_resolve_by_slot_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"broll-0002-custom.webp").write_bytes(b"x")
            manifest={"items":[{"slot_id":"broll-0002","output_filename":"different.png"}]}
            mapping,_=mod.resolve_folder(manifest,root)
            self.assertTrue(mapping["broll-0002"].endswith(".webp"))


if __name__=="__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).parents[1] / "tools" / "ai_edit" / "update_p5_ai_edit.py"
spec = importlib.util.spec_from_file_location("update_p5_ai_edit", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class FakeClient:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        names = ["kdenlive_checkpoint_project", "kdenlive_add_track", "kdenlive_import_media", "kdenlive_insert_bin_clip"]
        return [{"name": n, "input_schema": {"type": "object"}} for n in names]

    def call_tool(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        if name == "kdenlive_checkpoint_project":
            return {"ok": True, "result": {"ok": True, "path": "checkpoint.kdenlive"}}
        if name == "kdenlive_add_track":
            return {"ok": True, "result": {"ok": True, "track_id": 42}}
        if name == "kdenlive_import_media":
            return {"ok": True, "result": {"ok": True, "bin_id": "7"}}
        if name == "kdenlive_insert_bin_clip":
            return {"ok": True, "result": {"ok": True, "clip_id": 99}}
        raise AssertionError(name)


class AiEditTests(unittest.TestCase):
    def test_validate_duplicate_id(self):
        doc = {"format": mod.FORMAT, "version": 1, "steps": [
            {"id": "x", "tool": "kdenlive_get_timeline_state"},
            {"id": "x", "tool": "kdenlive_get_timeline_state"}
        ]}
        self.assertTrue(any("duplicates" in e for e in mod.validate_plan(doc)))

    def test_ref_resolution_and_apply(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            media = root / "input.mp4"
            media.write_bytes(b"")
            plan = root / "edit.json"
            doc = {
                "format": mod.FORMAT,
                "version": 1,
                "variables": {"MAIN": "./input.mp4"},
                "steps": [
                    {"id": "track", "tool": "kdenlive_add_track", "arguments": {"audio": False}},
                    {"id": "media", "tool": "kdenlive_import_media", "arguments": {"path": {"$var": "MAIN"}}},
                    {"id": "insert", "tool": "kdenlive_insert_bin_clip", "arguments": {
                        "bin_id": {"$ref": "media.result.bin_id"},
                        "track_id": {"$ref": "track.result.track_id"},
                        "position_seconds": 0
                    }}
                ]
            }
            plan.write_text(json.dumps(doc), encoding="utf-8")
            client = FakeClient()
            report = mod.apply_plan(plan, doc, client, mod._variables(doc, []), yes=True, checkpoint=True, continue_on_error=False)
            self.assertTrue(report["ok"])
            insert = [c for c in client.calls if c[0] == "kdenlive_insert_bin_clip"][0]
            self.assertEqual(insert[1]["bin_id"], "7")
            self.assertEqual(insert[1]["track_id"], 42)
            imported = [c for c in client.calls if c[0] == "kdenlive_import_media"][0]
            self.assertEqual(imported[1]["path"], str(media.resolve()))


if __name__ == "__main__":
    unittest.main()

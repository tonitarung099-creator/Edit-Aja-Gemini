import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


composer = load("ai_edit_compose", ROOT / "tools" / "ai_edit" / "compose.py")


class ComposeTests(unittest.TestCase):
    def plan(self, title, steps, variables=None):
        doc = {
            "format": "update-p5-ai-edit",
            "version": 1,
            "metadata": {"title": title},
            "steps": steps,
        }
        if variables is not None:
            doc["variables"] = variables
        return doc

    def test_prefixes_steps_and_rewrites_refs(self):
        first = self.plan(
            "A",
            [
                {"id": "import", "tool": "kdenlive_import_media", "arguments": {"path": "a.mp4"}},
                {
                    "id": "insert",
                    "tool": "kdenlive_insert_bin_clip",
                    "arguments": {"bin_id": {"$ref": "import.result.bin_id"}, "track_id": 1},
                },
                {"id": "save", "tool": "kdenlive_save_project", "arguments": {}},
            ],
        )
        second = self.plan(
            "B",
            [{"id": "save", "tool": "kdenlive_save_project", "arguments": {}}],
        )
        result = composer.compose_plans(
            [(Path("cut.json"), first), (Path("captions.json"), second)]
        )
        ids = [step["id"] for step in result["steps"]]
        self.assertEqual(ids, ["cut-import", "cut-insert", "save-final"])
        self.assertEqual(
            result["steps"][1]["arguments"]["bin_id"]["$ref"],
            "cut-import.result.bin_id",
        )

    def test_merges_matching_variables(self):
        a = self.plan("A", [{"id": "x", "tool": "kdenlive_save_project"}], {"MEDIA": ""})
        b = self.plan("B", [{"id": "y", "tool": "kdenlive_save_project"}], {"MEDIA": ""})
        result = composer.compose_plans([(Path("a.json"), a), (Path("b.json"), b)])
        self.assertEqual(result["variables"]["MEDIA"], "")

    def test_rejects_conflicting_variables(self):
        a = self.plan("A", [{"id": "x", "tool": "kdenlive_save_project"}], {"MEDIA": "a.mp4"})
        b = self.plan("B", [{"id": "y", "tool": "kdenlive_save_project"}], {"MEDIA": "b.mp4"})
        with self.assertRaises(composer.ComposeError):
            composer.compose_plans([(Path("a.json"), a), (Path("b.json"), b)])


if __name__ == "__main__":
    unittest.main()

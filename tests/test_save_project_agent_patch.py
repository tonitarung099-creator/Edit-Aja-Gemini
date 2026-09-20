import json
import unittest

from tests.build_contract import ROOT


PATCH = ROOT / "patches" / "save-project-agent.patch"
MANIFEST = ROOT / "build" / "build-manifest.json"
BLUEPRINT = ROOT / "craft" / "editaja" / "editaja.py"


class NativeSaveProjectPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_new_target_does_not_use_overwrite_permission_as_existing_file_flag(self):
        self.assertIn("const bool outputExists = output.exists();", self.patch)
        self.assertIn("if (outputExists && !overwrite)", self.patch)
        self.assertIn(
            "saveFileAs(output.absoluteFilePath(), outputExists && overwrite, saveCopy)",
            self.patch,
        )
        added = "\n".join(
            line[1:] for line in self.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertNotIn(
            "saveFileAs(output.absoluteFilePath(), overwrite, saveCopy)",
            added,
        )

    def test_save_fix_precedes_ui_sidebar_patch(self):
        names = [entry["name"] for entry in self.manifest["apply_chain"]]
        save_index = names.index("save-project-agent")
        ui_index = names.index("ai-agent-sidebar")
        self.assertLess(save_index, ui_index)
        entry = self.manifest["apply_chain"][save_index]
        self.assertEqual(entry["path"], "patches/save-project-agent.patch")
        self.assertTrue(entry["check"])

    def test_save_fix_is_copied_into_blueprint_before_ui_patch(self):
        payloads = {
            item["source"]: item["destination"]
            for item in self.manifest["blueprint_payloads"]
        }
        self.assertEqual(
            payloads["patches/save-project-agent.patch"],
            "craft/editaja/save-project-agent.patch",
        )
        chain = self.blueprint.split('self.patchToApply["editaja"] = ', 1)[1].split("\n", 1)[0]
        self.assertIn('("save-project-agent.patch", 1)', chain)
        self.assertIn('("ai-agent-sidebar.patch", 1)', chain)
        self.assertLess(
            chain.index('("save-project-agent.patch", 1)'),
            chain.index('("ai-agent-sidebar.patch", 1)'),
        )


if __name__ == "__main__":
    unittest.main()

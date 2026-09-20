import json
import unittest

from tests.build_contract import ROOT


PATCH = ROOT / "patches" / "keyframe-api-compile-fix.patch"
MANIFEST = ROOT / "build" / "build-manifest.json"
BLUEPRINT = ROOT / "craft" / "editaja" / "editaja.py"


class KeyframeApiCompileFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_uses_public_keyframe_model_list_api(self):
        self.assertIn("keyframes->removeAllKeyframes()", self.patch)
        self.assertIn("keyframes->addKeyframe(position, type)", self.patch)
        self.assertIn("keyframes->updateKeyframe(position, QVariant(value)", self.patch)

    def test_does_not_call_protected_keyframe_model_mutators(self):
        added = "\n".join(
            line[1:] for line in self.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertNotIn("rectModel->removeAllKeyframes()", added)
        self.assertNotIn("rectModel->addKeyframe(", added)

    def test_fix_precedes_native_save_patch(self):
        names = [entry["name"] for entry in self.manifest["apply_chain"]]
        keyframe = names.index("keyframe-api-compile-fix")
        save_fix = names.index("save-project-agent")
        self.assertLess(keyframe, save_fix)
        entry = self.manifest["apply_chain"][keyframe]
        self.assertEqual(entry["path"], "patches/keyframe-api-compile-fix.patch")
        self.assertTrue(entry["check"])
        self.assertTrue(entry["ignore_space_change"])

    def test_craft_blueprint_preserves_keyframe_before_save_fix(self):
        chain = self.blueprint.split('self.patchToApply["editaja"] = ', 1)[1].split("\n", 1)[0]
        self.assertIn('("keyframe-api-compile-fix.patch", 1)', chain)
        self.assertIn('("save-project-agent.patch", 1)', chain)
        self.assertLess(
            chain.index('("keyframe-api-compile-fix.patch", 1)'),
            chain.index('("save-project-agent.patch", 1)'),
        )


if __name__ == "__main__":
    unittest.main()

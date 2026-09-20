import base64
import bz2
import hashlib
import unittest

from tests.build_contract import ROOT, apply_entry, patch_entry


PATCH_FILE = ROOT / "patches" / "phase13-local-edit-scene-undo.patch.bz2.b64"
EXPECTED_SHA256 = "a553eb5f1213e055a95bd8653039e978e6ba950db2ff627e7b471aa176e9f39b"


class LocalEditSceneUndoPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        encoded = PATCH_FILE.read_text(encoding="ascii")
        raw = bz2.decompress(base64.b64decode(encoded))
        cls.patch = raw.decode("utf-8")
        cls.digest = hashlib.sha256(raw).hexdigest()

    def test_checksum(self):
        self.assertEqual(self.digest, EXPECTED_SHA256)

    def test_scene_detection_map_contract(self):
        self.assertIn("kdenlive_get_scene_map", self.patch)
        self.assertIn("scene_detection_markers", self.patch)
        self.assertIn("marker.hasRange()", self.patch)
        self.assertIn("Point markers from Kdenlive Scene Detection are cut boundaries", self.patch)
        self.assertIn('i18n("Scene %1", lastNumber + 1)', self.patch)
        self.assertIn("timeline_start_frame", self.patch)
        self.assertIn("timeline_end_frame", self.patch)

    def test_local_edit_prefers_detected_scene_ranges(self):
        self.assertIn("Detected Scene %1 deleted using Scene Detection markers", self.patch)
        self.assertIn("kdenlive_remove_ranges", self.patch)
        self.assertIn("ordered clip fallback", self.patch)

    def test_multi_snapshot_is_one_undo_macro(self):
        self.assertIn('beginMacro(i18n("Local Edit: Zoom snapshots"))', self.patch)
        self.assertGreaterEqual(self.patch.count("endMacro()"), 2)

    def test_detected_scene_remove_ranges_initializer_is_balanced(self):
        self.assertIn(
            '{QStringLiteral("end_frame"), endFrame}}}},',
            self.patch,
        )
        self.assertNotIn(
            '{QStringLiteral("end_frame"), endFrame}}}}},',
            self.patch,
        )

    def test_build_chain_contains_phase13(self):
        blueprint = (ROOT / "craft" / "editaja" / "editaja.py").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts" / "verify_p5_source.py").read_text(encoding="utf-8")

        patch = patch_entry("phase13")
        apply = apply_entry("phase13")

        self.assertIn('("phase13.patch", 1)', blueprint)
        self.assertEqual(patch["sha256"], EXPECTED_SHA256)
        self.assertEqual(patch["sources"], ["patches/phase13-local-edit-scene-undo.patch.bz2.b64"])
        self.assertEqual(patch["output"], "craft/editaja/phase13.patch")
        self.assertEqual(apply["strip"], 1)
        self.assertIn("kdenlive_get_scene_map", verifier)
        self.assertIn("Local Edit: Zoom snapshots", verifier)


if __name__ == "__main__":
    unittest.main()

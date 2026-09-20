import base64
import bz2
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "build" / "build-manifest.json"


class BuildManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_revisions_are_pinned_full_commit_shas(self):
        for label, value in (
            ("Kdenlive", self.manifest["upstream"]["commit"]),
            ("Craft", self.manifest["craft"]["revision"]),
        ):
            self.assertRegex(value, r"^[0-9a-f]{40}$", f"{label} must be pinned to a full commit SHA")

        self.assertIn(
            self.manifest["craft"]["revision"],
            self.manifest["craft"]["bootstrap_url"],
            "Craft bootstrap URL must be pinned to the same Craft revision",
        )

    def test_blueprint_upstream_commit_matches_manifest(self):
        blueprint = (ROOT / "craft" / "editaja" / "editaja.py").read_text(encoding="utf-8")
        match = re.search(r'^UPSTREAM_COMMIT = "([0-9a-f]{40})"$', blueprint, flags=re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), self.manifest["upstream"]["commit"])

    def test_compressed_patch_checksums_match_manifest(self):
        for patch in self.manifest["patches"]:
            encoded = "".join(
                (ROOT / source).read_text(encoding="utf-8") for source in patch["sources"]
            )
            data = bz2.decompress(base64.b64decode(encoded))
            digest = hashlib.sha256(data).hexdigest()
            self.assertEqual(digest, patch["sha256"], patch["name"])

    def test_generated_patch_outputs_are_in_apply_chain(self):
        apply_paths = {entry["path"] for entry in self.manifest["apply_chain"]}
        for patch in self.manifest["patches"]:
            self.assertIn(patch["output"], apply_paths)

    def test_windows_build_scripts_are_explicit(self):
        required = {
            "bootstrap-craft.ps1",
            "collect-package.ps1",
            "craft-env.ps1",
            "install-blueprint.ps1",
            "invoke-craft.ps1",
            "patch-gettext.ps1",
            "reconstruct-source.ps1",
        }
        actual = {path.name for path in (ROOT / "scripts" / "windows").glob("*.ps1")}
        self.assertTrue(required.issubset(actual))

    def test_cross_platform_source_reconstruction_is_canonical(self):
        shared = ROOT / "scripts" / "reconstruct_source.py"
        wrapper = ROOT / "scripts" / "windows" / "reconstruct-source.ps1"
        self.assertTrue(shared.is_file())
        self.assertIn(
            "python scripts/reconstruct_source.py",
            wrapper.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()

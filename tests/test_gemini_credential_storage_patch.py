import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "gemini-credential-storage.patch"
MANIFEST = ROOT / "build" / "build-manifest.json"
BLUEPRINT = ROOT / "craft" / "editaja" / "editaja.py"
EXPECTED_SHA256 = "72bdfe43d74087e788bf6292ce81c6f3890f3bf7b33e5205dd73dbc4eb579947"


class GeminiCredentialStoragePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch_bytes = PATCH.read_bytes()
        cls.patch = cls.patch_bytes.decode("utf-8")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_patch_checksum_and_expected_surface(self):
        self.assertEqual(hashlib.sha256(self.patch_bytes).hexdigest(), EXPECTED_SHA256)
        changed = []
        for line in self.patch.splitlines():
            if line.startswith("diff --git a/"):
                changed.append(line.split(" b/", 1)[0].removeprefix("diff --git a/"))
        self.assertEqual(
            changed,
            [
                "src/CMakeLists.txt",
                "src/aiassistant/CMakeLists.txt",
                "src/aiassistant/aiassistantwidget.cpp",
                "src/aiassistant/aiassistantwidget.h",
                "src/aiassistant/geminicredentialstore.cpp",
                "src/aiassistant/geminicredentialstore.h",
            ],
        )

    def test_windows_credential_manager_api_is_used(self):
        for marker in (
            "CredEnumerateW",
            "CredWriteW",
            "CredDeleteW",
            "CRED_TYPE_GENERIC",
            "CRED_PERSIST_LOCAL_MACHINE",
            "advapi32",
        ):
            self.assertIn(marker, self.patch)

    def test_secret_is_not_persisted_through_qsettings(self):
        added = "\n".join(
            line[1:] for line in self.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertNotIn('setValue(QStringLiteral("geminiApiKey")', added)
        self.assertNotIn('setValue(QStringLiteral("apiKey")', added)
        self.assertIn("never written to project files or QSettings", added)

    def test_secure_storage_is_optional_and_session_fallback_is_explicit(self):
        self.assertIn("Remember API keys securely on this Windows PC", self.patch)
        self.assertIn("secure Windows storage failed", self.patch)
        self.assertIn("The key is available for this session", self.patch)
        self.assertIn("saved securely", self.patch)

    def test_build_chain_places_storage_after_hardening(self):
        names = [entry["name"] for entry in self.manifest["apply_chain"]]
        self.assertEqual(
            names[-3:],
            ["gemini-native", "gemini-hardening", "gemini-credential-storage"],
        )
        entry = self.manifest["apply_chain"][-1]
        self.assertEqual(entry["path"], "craft/editaja/gemini-credential-storage.patch")
        self.assertTrue(entry["check"])
        self.assertTrue(entry["ignore_space_change"])
        payloads = {
            item["source"]: item["destination"]
            for item in self.manifest["blueprint_payloads"]
        }
        self.assertEqual(
            payloads["patches/gemini-credential-storage.patch"],
            "craft/editaja/gemini-credential-storage.patch",
        )
        chain = self.blueprint.split('self.patchToApply["editaja"] = ', 1)[1].split("\n", 1)[0]
        self.assertTrue(chain.rstrip().endswith('("gemini-credential-storage.patch", 1)]'))


if __name__ == "__main__":
    unittest.main()

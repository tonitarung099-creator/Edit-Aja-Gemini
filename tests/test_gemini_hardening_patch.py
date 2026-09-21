import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches" / "gemini-hardening.patch"
MANIFEST = ROOT / "build" / "build-manifest.json"
BLUEPRINT = ROOT / "craft" / "editaja" / "editaja.py"
EXPECTED_SHA256 = "5f287fada507e3a187e25974fd9d9de5d0b74d4b76202b36dd0dd0df2e7bc433"


class GeminiHardeningPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch_bytes = PATCH.read_bytes()
        cls.patch = cls.patch_bytes.decode("utf-8")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_patch_checksum_and_surface(self):
        self.assertEqual(hashlib.sha256(self.patch_bytes).hexdigest(), EXPECTED_SHA256)
        changed = []
        for line in self.patch.splitlines():
            if line.startswith("diff --git a/"):
                changed.append(line.split(" b/", 1)[0].removeprefix("diff --git a/"))
        self.assertEqual(
            changed,
            [
                "src/aiassistant/geminiagent.cpp",
                "src/aiassistant/geminiagent.h",
            ],
        )

    def test_cancel_invalidates_stale_callbacks(self):
        self.assertGreaterEqual(self.patch.count("++m_requestEpoch"), 3)
        self.assertIn("const quint64 requestEpoch = m_requestEpoch;", self.patch)
        self.assertGreaterEqual(self.patch.count("requestEpoch != m_requestEpoch"), 2)

    def test_sampling_override_is_removed(self):
        self.assertIn(
            '-        {QStringLiteral("generationConfig"), QJsonObject{{QStringLiteral("temperature"), 0.1}}},',
            self.patch,
        )
        added = "\n".join(
            line[1:] for line in self.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertNotIn('QStringLiteral("temperature")', added)
        self.assertNotIn('QStringLiteral("generationConfig")', added)

    def test_vision_parts_share_tool_response_turn(self):
        self.assertIn("Selected local frames for visual inspection; these are not the whole movie.", self.patch)
        self.assertIn("responseParts.push_back(visionPart);", self.patch)
        self.assertIn(
            '-            m_contents.push_back(QJsonObject{{QStringLiteral("role"), QStringLiteral("user")}, {QStringLiteral("parts"), visionParts}});',
            self.patch,
        )

    def test_build_chain_applies_hardening_after_native_gemini(self):
        names = [entry["name"] for entry in self.manifest["apply_chain"]]
        self.assertEqual(names[-2:], ["gemini-native", "gemini-hardening"])
        self.assertEqual(
            self.manifest["apply_chain"][-1]["path"],
            "craft/editaja/gemini-hardening.patch",
        )
        payloads = {
            item["source"]: item["destination"]
            for item in self.manifest["blueprint_payloads"]
        }
        self.assertEqual(
            payloads["patches/gemini-hardening.patch"],
            "craft/editaja/gemini-hardening.patch",
        )
        chain = self.blueprint.split('self.patchToApply["editaja"] = ', 1)[1].split("\n", 1)[0]
        self.assertTrue(
            chain.rstrip().endswith(
                '("gemini-native.patch", 1), ("gemini-hardening.patch", 1)]'
            )
        )


if __name__ == "__main__":
    unittest.main()

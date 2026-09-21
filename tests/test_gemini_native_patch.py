import base64
import bz2
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = sorted((ROOT / "patches").glob("gemini-native.patch.bz2.b64.*"))
MANIFEST = ROOT / "build" / "build-manifest.json"
BLUEPRINT = ROOT / "craft" / "editaja" / "editaja.py"


class GeminiNativePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoded = "".join(path.read_text(encoding="utf-8") for path in CHUNKS)
        cls.patch_bytes = bz2.decompress(base64.b64decode(cls.encoded))
        cls.patch = cls.patch_bytes.decode("utf-8")
        cls.digest = hashlib.sha256(cls.patch_bytes).hexdigest()
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_patch_chunks_and_checksum_are_pinned(self):
        self.assertEqual(len(CHUNKS), 3)
        entry = next(item for item in self.manifest["patches"] if item["name"] == "gemini-native")
        self.assertEqual(entry["sha256"], self.digest)
        self.assertEqual(
            entry["sources"],
            [str(path.relative_to(ROOT)).replace("\\", "/") for path in CHUNKS],
        )
        self.assertEqual(entry["output"], "craft/editaja/gemini-native.patch")

    def test_native_gemini_transport_markers_exist(self):
        for marker in (
            "Gemini",
            "x-goog-api-key",
            "generateContent",
            "functionCall",
            "m_requestEpoch",
            "requestEpoch != m_requestEpoch",
            "Selected local frames for visual inspection",
            "src/aiassistant/geminiagent.cpp",
        ):
            self.assertIn(marker, self.patch)

    def test_hardening_avoids_deprecated_sampling_and_split_vision_turns(self):
        self.assertNotIn('QStringLiteral("temperature")', self.patch)
        self.assertNotIn('QStringLiteral("generationConfig")', self.patch)
        self.assertNotIn('QStringLiteral("parts"), visionParts', self.patch)

    def test_gemini_patch_is_last_after_sidebar(self):
        names = [item["name"] for item in self.manifest["apply_chain"]]
        self.assertEqual(names[-2:], ["ai-agent-sidebar", "gemini-native"])
        self.assertEqual(self.manifest["apply_chain"][-1]["path"], "craft/editaja/gemini-native.patch")
        chain_line = self.blueprint.split('self.patchToApply["editaja"] = ', 1)[1].split("\n", 1)[0]
        self.assertTrue(chain_line.rstrip().endswith('("gemini-native.patch", 1)]'))

    def test_patch_changes_only_ai_assistant_native_surface(self):
        changed = []
        for line in self.patch.splitlines():
            if line.startswith("diff --git a/"):
                changed.append(line.split(" b/", 1)[0].removeprefix("diff --git a/"))
        self.assertTrue(changed)
        for path in changed:
            self.assertTrue(
                path.startswith("src/aiassistant/"),
                f"Unexpected Gemini patch target: {path}",
            )


if __name__ == "__main__":
    unittest.main()

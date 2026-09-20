import base64
import bz2
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = sorted((ROOT / "patches").glob("gemini-native.patch.bz2.b64.*"))


class GeminiNativePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encoded = "".join(path.read_text(encoding="utf-8") for path in CHUNKS)
        cls.patch_bytes = bz2.decompress(base64.b64decode(cls.encoded))
        cls.patch = cls.patch_bytes.decode("utf-8")
        cls.digest = hashlib.sha256(cls.patch_bytes).hexdigest()
        print(f"GEMINI_NATIVE_SHA256={cls.digest}")

    def test_patch_chunks_are_complete(self):
        self.assertEqual(len(CHUNKS), 3)
        self.assertGreater(len(self.patch_bytes), 1000)

    def test_native_gemini_transport_markers_exist(self):
        for marker in (
            "Gemini",
            "x-goog-api-key",
            "generateContent",
            "functionCall",
        ):
            self.assertIn(marker, self.patch)

    def test_patch_changes_ai_assistant_source(self):
        self.assertIn("src/aiassistant/", self.patch)
        self.assertIn("diff --git", self.patch)


if __name__ == "__main__":
    unittest.main()

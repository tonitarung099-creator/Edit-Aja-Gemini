import base64
import bz2
import hashlib
import unittest

from tests.build_contract import ROOT, apply_entry, patch_entry, payload_entry


PATCH = ROOT / "patches" / "phase15-film-context-native.patch.bz2.b64"
EXPECTED_SHA256 = "a8dc28c9e679d65d0551f997515ee0603983e373d1ab545def8d7fd5593e217a"


class FilmContextNativePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = bz2.decompress(base64.b64decode(PATCH.read_text(encoding="ascii")))
        cls.patch = raw.decode("utf-8")
        cls.digest = hashlib.sha256(raw).hexdigest()

    def test_checksum(self):
        self.assertEqual(self.digest, EXPECTED_SHA256)

    def test_optional_ui_exists(self):
        self.assertIn("Film Context", self.patch)
        self.assertIn("Enable Film Context tools for the AI agent", self.patch)
        self.assertIn("filmContextEnabled", self.patch)
        self.assertIn("Build Index", self.patch)
        self.assertIn("Build Visual Index (Optional)", self.patch)
        self.assertIn("filmContextOperation", self.patch)

    def test_agent_tool_surface(self):
        for name in (
            "movie_context_status",
            "movie_search",
            "movie_get_scene",
            "movie_get_context",
            "movie_get_keyframes",
        ):
            self.assertIn(name, self.patch)

    def test_local_backend_is_installed(self):
        self.assertIn("filmcontext/film_context.py", self.patch)
        blueprint = (ROOT / "craft" / "editaja" / "editaja.py").read_text(encoding="utf-8")
        self.assertIn('("phase15.patch", 1)', blueprint)
        self.assertIn("film_context.txt", blueprint)

    def test_small_vision_escalation(self):
        self.assertIn("agent_image_paths", self.patch)
        self.assertIn("movie_get_keyframes", self.patch)
        self.assertIn("Never request the whole film", self.patch)

    def test_windows_build_contract(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts" / "verify_p5_source.py").read_text(encoding="utf-8")
        reconstruct = (ROOT / "scripts" / "reconstruct_source.py").read_text(encoding="utf-8")
        windows_wrapper = (ROOT / "scripts" / "windows" / "reconstruct-source.ps1").read_text(encoding="utf-8")
        gettext_patcher = (ROOT / "scripts" / "patch_gettext_blueprint.py").read_text(encoding="utf-8")

        patch = patch_entry("phase15")
        apply = apply_entry("phase15")
        payload = payload_entry("tools/film_context/film_context.py")

        self.assertEqual(patch["sha256"], EXPECTED_SHA256)
        self.assertEqual(patch["sources"], ["patches/phase15-film-context-native.patch.bz2.b64"])
        self.assertEqual(patch["output"], "craft/editaja/phase15.patch")
        self.assertEqual(apply["strip"], 1)
        self.assertEqual(payload["destination"], "craft/editaja/film_context.txt")
        self.assertIn("film_context.py", reconstruct)
        self.assertIn("shutil.copy2", reconstruct)
        self.assertIn("python scripts/reconstruct_source.py", windows_wrapper)
        self.assertIn("movie_search", verifier)
        self.assertIn("Build Visual Index", verifier)
        self.assertIn("Patch Craft gettext MinGW libxml2 linking", workflow)
        self.assertIn("P5 Quality Gates", workflow)
        self.assertIn("workflow_run", workflow)
        self.assertIn("LIBS=-lxml2", gettext_patcher)

    def test_ai_edit_json_stays_separate(self):
        docs = (ROOT / "docs" / "features" / "FILM_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("Film Context itself never edits the timeline", docs)
        self.assertIn("AI Edit JSON", docs)


if __name__ == "__main__":
    unittest.main()

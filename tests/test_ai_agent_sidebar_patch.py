import json
import unittest

from tests.build_contract import ROOT


PATCH = ROOT / "patches" / "ai-agent-sidebar.patch"
MANIFEST = ROOT / "build" / "build-manifest.json"
BLUEPRINT = ROOT / "craft" / "editaja" / "editaja.py"


class AiAgentSidebarPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.blueprint = BLUEPRINT.read_text(encoding="utf-8")

    def test_agent_is_primary_right_sidebar(self):
        self.assertIn('addDock(i18n("AI Agent")', self.patch)
        self.assertIn("m_aiAssistantDock->open();", self.patch)
        self.assertIn("m_aiAssistantDock->setAsCurrentTab();", self.patch)
        self.assertIn("Keep AI Agent as the primary right sidebar", self.patch)
        self.assertIn("m_effectStackDock->addDockWidgetAsTab(m_aiAssistantDock);", self.patch)

    def test_sidebar_is_scrollable_and_main_control_is_first_class(self):
        self.assertIn("#include <QScrollArea>", self.patch)
        self.assertIn('setObjectName(QStringLiteral("aiAssistantScrollArea"))', self.patch)
        self.assertIn('QGroupBox(i18n("AI Agent — Main Control")', self.patch)
        self.assertIn("m_output->setMinimumHeight(220);", self.patch)

    def test_old_default_hidden_behavior_is_removed(self):
        added = "\n".join(
            line[1:] for line in self.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertNotIn("m_aiAssistantDock->close();", added)

    def test_sidebar_precedes_gemini_layers_and_is_copied_to_craft(self):
        entries = self.manifest["apply_chain"]
        names = [entry["name"] for entry in entries]
        self.assertEqual(
            names[-4:],
            ["ai-agent-sidebar", "gemini-native", "gemini-hardening", "gemini-credential-storage"],
        )
        entry = entries[-4]
        self.assertEqual(entry["path"], "patches/ai-agent-sidebar.patch")
        self.assertTrue(entry["check"])
        payloads = {
            item["source"]: item["destination"]
            for item in self.manifest["blueprint_payloads"]
        }
        self.assertEqual(
            payloads["patches/ai-agent-sidebar.patch"],
            "craft/editaja/ai-agent-sidebar.patch",
        )
        chain = self.blueprint.split('self.patchToApply["editaja"] = ', 1)[1].split("\n", 1)[0]
        self.assertIn(
            '("ai-agent-sidebar.patch", 1), ("gemini-native.patch", 1), ("gemini-hardening.patch", 1), ("gemini-credential-storage.patch", 1)]',
            chain,
        )


if __name__ == "__main__":
    unittest.main()

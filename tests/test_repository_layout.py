import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ROOT_MARKDOWN = {
    "AGENTS.md",
    "README.md",
    "BUILDING.md",
    "ROADMAP.md",
    "LICENSE-NOTE.md",
}

ALLOWED_WORKFLOW_YAML = {
    "build-windows.yml",
    "quality-gates.yml",
}


class RepositoryLayoutTests(unittest.TestCase):
    def test_repository_root_stays_focused(self):
        markdown = {
            path.name
            for path in ROOT.glob("*.md")
            if path.is_file()
        }
        self.assertEqual(markdown, ALLOWED_ROOT_MARKDOWN)

    def test_feature_documentation_has_an_index(self):
        feature_docs = ROOT / "docs" / "features"
        self.assertTrue((feature_docs / "README.md").is_file())
        self.assertTrue((feature_docs / "LOCAL_EDIT_AGENT.md").is_file())
        self.assertTrue((feature_docs / "FILM_CONTEXT.md").is_file())

    def test_examples_are_centralized(self):
        examples = ROOT / "examples"
        for name in ("caption", "creator", "dialogue", "documentary", "segmentation"):
            self.assertTrue((examples / name).is_dir(), name)
            self.assertFalse((ROOT / name).exists(), f"{name}/ should live below examples/")

    def test_workflow_surface_stays_small(self):
        workflow_dir = ROOT / ".github" / "workflows"
        yaml_files = {
            path.name
            for path in workflow_dir.glob("*.yml")
            if path.is_file()
        }
        self.assertEqual(yaml_files, ALLOWED_WORKFLOW_YAML)

    def test_no_feature_specific_test_workflows_return(self):
        workflow_dir = ROOT / ".github" / "workflows"
        per_feature = [
            path.name
            for path in workflow_dir.glob("test-*.yml")
        ]
        self.assertEqual(per_feature, [])


if __name__ == "__main__":
    unittest.main()

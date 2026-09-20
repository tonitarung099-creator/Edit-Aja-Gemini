import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from reconstruct_source import write_source_archive


class SourceArchiveTests(unittest.TestCase):
    def test_archive_excludes_git_metadata_without_deleting_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            source = temp_root / "source"
            git_pack = source / ".git" / "objects" / "pack"
            git_pack.mkdir(parents=True)
            (git_pack / "pack-test.idx").write_bytes(b"git metadata")

            (source / "src").mkdir()
            (source / "src" / "main.cpp").write_text(
                "int main() { return 0; }\n",
                encoding="utf-8",
            )

            archive_path = temp_root / "source.zip"
            write_source_archive(source, archive_path)

            self.assertTrue((source / ".git").is_dir())
            self.assertTrue((git_pack / "pack-test.idx").is_file())

            with zipfile.ZipFile(archive_path) as archive:
                names = set(archive.namelist())

            self.assertIn("src/main.cpp", names)
            self.assertFalse(
                any(name == ".git" or name.startswith(".git/") for name in names)
            )


if __name__ == "__main__":
    unittest.main()

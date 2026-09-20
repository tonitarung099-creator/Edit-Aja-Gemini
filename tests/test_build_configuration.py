import configparser
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.configure_craft import configure


class CraftConfigurationTests(unittest.TestCase):
    def configure_text(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CraftSettings.ini"
            path.write_text(text, encoding="utf-8-sig")
            with contextlib.redirect_stdout(io.StringIO()):
                configure(path)
                first = path.read_bytes()
                configure(path)
            self.assertEqual(first, path.read_bytes(), "Configuration must be idempotent")
            config = configparser.ConfigParser(interpolation=None)
            config.read(path, encoding="utf-8")
            return config

    def test_bootstrap_without_short_path_section(self):
        config = self.configure_text("[General]\nABI=windows-cl-msvc2022-x86_64\n")
        self.assertEqual(config["ShortPath"]["DriveLetter"], "Z:/")
        self.assertEqual(config["General"]["ABI"], "windows-gcc-x86_64")
        self.assertEqual(config["Compile"]["BuildType"], "RelWithDebInfo")
        self.assertTrue(config.getboolean("Packager", "UseCache"))

    def test_existing_sections_and_unrelated_values_are_preserved(self):
        config = self.configure_text(
            "[ShortPath]\n#DriveLetter = Z:/\nJunctionDir=C:/_\n"
            "[Compile]\nBuildType=Debug\nJobs=4\n"
            "[Paths]\nPython=C:/Python311\n"
            "[Packager]\nRepositoryUrl=https://files.kde.org/craft/Qt6/\n"
            "[Blueprints]\nBlueprintRoot=${Variables:CraftRoot}/etc/blueprints/locations\n"
        )
        self.assertEqual(config["ShortPath"]["DriveLetter"], "Z:/")
        self.assertEqual(config["ShortPath"]["JunctionDir"], "C:/_")
        self.assertEqual(config["Compile"]["Jobs"], "4")
        self.assertEqual(config["Paths"]["Python"], "C:/Python311")
        self.assertEqual(config["Packager"]["RepositoryUrl"], "https://files.kde.org/craft/Qt6/")
        self.assertEqual(config["Blueprints"]["BlueprintRoot"], "${Variables:CraftRoot}/etc/blueprints/locations")

    def test_existing_drive_is_replaced_without_duplicate_key(self):
        config = self.configure_text("[ShortPath]\ndriveletter=Y:/\n")
        self.assertEqual(dict(config["ShortPath"]), {"driveletter": "Z:/"})

    def test_missing_bootstrap_configuration_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.ini"
            with self.assertRaises(FileNotFoundError):
                configure(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

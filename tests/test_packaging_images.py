import os
import sys
import tempfile
from enum import IntFlag
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import unittest
from pathlib import Path

from scripts.prepare_package_images import compatible_image_candidates, create_windows_junction, prepare


class PackagingImageTests(unittest.TestCase):
    def test_prefers_minsizerel_compatible_image_for_same_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "image-MinSizeRel-14.2.0").mkdir()
            (root / "image-Release-14.2.0").mkdir()
            candidates = compatible_image_candidates(
                root, "image-RelWithDebInfo-14.2.0"
            )
            self.assertEqual(
                [path.name for path in candidates],
                ["image-MinSizeRel-14.2.0", "image-Release-14.2.0"],
            )

    def test_ignores_debug_symbols_and_other_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "image-MinSizeRel-14.2.0-dbg").mkdir()
            (root / "image-MinSizeRel-13.2.0").mkdir()
            self.assertEqual(
                compatible_image_candidates(root, "image-RelWithDebInfo-14.2.0"),
                [],
            )


    def test_rejects_debug_unknown_and_suffix_matched_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("image-Debug-14.2.0", "image-Custom-14.2.0", "image-MinSizeRel-custom-14.2.0"):
                (root / name).mkdir()
            self.assertEqual(compatible_image_candidates(root, "image-RelWithDebInfo-14.2.0"), [])
            (root / "image-MinSizeRel-14.2.0").mkdir()
            self.assertEqual(compatible_image_candidates(root, "image-Debug-14.2.0"), [])

    @unittest.skipUnless(os.name == "nt", "Windows junction integration")
    def test_windows_junction_exposes_runtime_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "image-MinSizeRel-14.2.0"
            destination = root / "image-RelWithDebInfo-14.2.0"
            source.mkdir()
            (source / "runtime.dll").write_bytes(b"runtime fixture")
            try:
                create_windows_junction(source, destination)
                self.assertEqual((destination / "runtime.dll").read_bytes(), b"runtime fixture")
                self.assertTrue(destination.samefile(source))
                with self.assertRaises(RuntimeError):
                    create_windows_junction(source, destination)
            finally:
                if destination.is_dir():
                    os.rmdir(destination)
            self.assertEqual((source / "runtime.dll").read_bytes(), b"runtime fixture")


class PackagingPreflightTests(unittest.TestCase):
    """Exercise the helper's dependency contract; Windows CI covers mklink itself."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "craft/bin").mkdir(parents=True)
        (self.root / "craft/craftenv.ps1").touch()
        (self.root / "etc").mkdir()
        (self.root / "etc/CraftSettings.ini").touch()
        env_patch = patch.dict(os.environ, {})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.dependencies = []
        self.ignored = ["libs/llvm"]
        self.owner = SimpleNamespace(ignoredPackages=self.ignored)

        class DependencyType(IntFlag):
            Runtime = 1
            Packaging = 8

        class SourceOnly:
            pass

        class BinaryPackage:
            pass

        self.source_only = SourceOnly
        self.binary_package = BinaryPackage
        self.dep_type = DependencyType
        package_module = ModuleType("Blueprints.CraftPackageObject")
        package_module.CraftPackageObject = SimpleNamespace(get=lambda name: SimpleNamespace(path=name, instance=self.owner))
        dependency_module = ModuleType("Blueprints.CraftDependencyPackage")
        dependency_module.DependencyType = DependencyType
        dependency_module.CraftDependencyPackage = lambda package: SimpleNamespace(getDependencies=self.resolve)
        source_module = ModuleType("Package.SourceOnlyPackageBase")
        source_module.SourceOnlyPackageBase = SourceOnly
        binary_module = ModuleType("Package.BinaryPackageBase")
        binary_module.BinaryPackageBase = BinaryPackage
        modules = {
            "Blueprints.CraftPackageObject": package_module,
            "Blueprints.CraftDependencyPackage": dependency_module,
            "Package.SourceOnlyPackageBase": source_module,
            "Package.BinaryPackageBase": binary_module,
        }
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.path_patch = patch.object(sys, "path", list(sys.path))
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def resolve(self, *, depType, ignoredPackages):
        self.assertEqual(depType, self.dep_type.Runtime | self.dep_type.Packaging)
        self.assertIs(ignoredPackages, self.ignored)
        return self.dependencies

    def dependency(self, name, desired_exists=False, alternative="MinSizeRel", binary=False):
        root = self.root / name
        root.mkdir(parents=True)
        desired = root / "image-RelWithDebInfo-14.2.0"
        if desired_exists:
            desired.mkdir()
        if alternative:
            (root / f"image-{alternative}-14.2.0").mkdir()
        instance = self.binary_package() if binary else SimpleNamespace()
        instance.imageDir = lambda: desired
        self.dependencies.append(SimpleNamespace(path=name, instance=instance))
        return desired

    def installer_dependency(self, *, desired_exists=False, alternative="MinSizeRel", payload=True, binary=True):
        desired = self.dependency("dev-utils/7zip-base", desired_exists, alternative, binary)
        seven_zip = self.dependencies.pop()  # intentionally outside the app graph
        package_module = sys.modules["Blueprints.CraftPackageObject"]
        package_module.CraftPackageObject.get = lambda name: seven_zip if name == seven_zip.path else SimpleNamespace(path=name, instance=self.owner)
        compiler = ModuleType("CraftCompiler")
        compiler.CraftCompiler = SimpleNamespace(Architecture=SimpleNamespace(x86_64="x64"))
        core = ModuleType("CraftCore")
        core.CraftCore = SimpleNamespace(compiler=SimpleNamespace(architecture="x64"))
        sys.modules["CraftCompiler"] = compiler
        sys.modules["CraftCore"] = core
        image = desired if desired_exists else desired.parent / f"image-{alternative}-14.2.0"
        if payload:
            (image / "dev-utils/7z/x64").mkdir(parents=True)
            (image / "dev-utils/7z/x64/7za.exe").write_bytes(b"fixture")
        return desired

    def test_installer_tool_outside_app_graph_is_repaired_and_verified(self):
        desired = self.installer_dependency()
        with patch("scripts.prepare_package_images.create_windows_junction") as junction, patch("scripts.prepare_package_images.verify_installer_tools") as verify:
            self.assertEqual(prepare(self.root, "application", check_installer_tools=True), 0)
            junction.assert_called_once_with(desired.parent / "image-MinSizeRel-14.2.0", desired)
            verify.assert_called_once_with()

    def test_missing_x64_payload_prevents_all_junctions(self):
        self.dependency("libs/runtime")
        self.installer_dependency(payload=False)
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            with self.assertRaisesRegex(RuntimeError, "7zip-base"):
                prepare(self.root, "application", check_installer_tools=True)
            junction.assert_not_called()

    def test_existing_but_incomplete_installer_image_is_rejected(self):
        self.installer_dependency(desired_exists=True, payload=False)
        with self.assertRaisesRegex(RuntimeError, "7za.exe"):
            prepare(self.root, "application", check_installer_tools=True)

    def test_source_built_installer_tool_is_rejected(self):
        self.installer_dependency(binary=False)
        with self.assertRaisesRegex(RuntimeError, "7zip-base"):
            prepare(self.root, "application", check_installer_tools=True)

    def test_installer_tool_execution_failure_propagates(self):
        self.installer_dependency(desired_exists=True)
        with patch("scripts.prepare_package_images.verify_installer_tools", side_effect=RuntimeError("broken tool")):
            with self.assertRaisesRegex(RuntimeError, "broken tool"):
                prepare(self.root, "application", check_installer_tools=True)

    def test_prebuilt_snoretoast_can_reuse_same_version_release_image(self):
        desired = self.dependency("dev-utils/snoretoast", binary=True)
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            self.assertEqual(prepare(self.root, "application"), 0)
            junction.assert_called_once_with(desired.parent / "image-MinSizeRel-14.2.0", desired)

    def test_source_built_snoretoast_is_not_aliased(self):
        self.dependency("dev-utils/snoretoast")
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            with self.assertRaisesRegex(RuntimeError, "snoretoast"):
                prepare(self.root, "application")
            junction.assert_not_called()

    def test_early_check_skips_only_application_image(self):
        self.dependency("application", alternative=None)
        self.dependency("dependency", alternative=None)
        with self.assertRaisesRegex(RuntimeError, "dependency"):
            prepare(self.root, "application", dependencies_only=True)
        self.dependencies.pop()
        self.assertEqual(prepare(self.root, "application", dependencies_only=True), 0)
        with self.assertRaisesRegex(RuntimeError, "application"):
            prepare(self.root, "application")

    def test_runtime_fallback_is_used_and_existing_images_untouched(self):
        desired = self.dependency("libs/runtime")
        self.dependency("application", desired_exists=True)
        self.dependencies.append(SimpleNamespace(path="source-only", instance=self.source_only()))
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            self.assertEqual(prepare(self.root, "application"), 0)
            junction.assert_called_once_with(desired.parent / "image-MinSizeRel-14.2.0", desired)

    def test_missing_application_prevents_all_mutations(self):
        self.dependency("libs/runtime")
        desired = self.dependency("application")
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            with self.assertRaisesRegex(RuntimeError, "application"):
                prepare(self.root, "application")
            junction.assert_not_called()
        self.assertFalse(desired.exists())

    def test_existing_runtime_is_idempotent(self):
        self.dependency("libs/runtime", desired_exists=True)
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            self.assertEqual(prepare(self.root, "application"), 0)
            junction.assert_not_called()

    def test_debug_runtime_is_not_a_release_fallback(self):
        self.dependency("libs/runtime", alternative="Debug")
        with patch("scripts.prepare_package_images.create_windows_junction") as junction:
            with self.assertRaisesRegex(RuntimeError, "libs/runtime"):
                prepare(self.root, "application")
            junction.assert_not_called()

    def test_junction_failure_is_not_reported_as_success(self):
        self.dependency("libs/runtime")
        with patch("scripts.prepare_package_images.create_windows_junction", side_effect=RuntimeError("mklink failed")):
            with self.assertRaisesRegex(RuntimeError, "mklink failed"):
                prepare(self.root, "application")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Prepare Craft dependency image directories required by Windows packaging."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def compatible_image_candidates(build_root: Path, desired_name: str) -> list[Path]:
    """Return compatible sibling image directories for a missing Craft image."""
    if not desired_name.startswith("image-"):
        return []
    parts = desired_name.split("-", 2)
    if len(parts) != 3:
        return []
    _, build_type, target = parts
    release_types = ("MinSizeRel", "Release", "RelWithDebInfo")
    if build_type not in release_types or not target or target.endswith("-dbg"):
        return []
    # Exact names: never substitute another version, a Debug build, or a
    # similarly suffixed target (for example custom-14.2.0 for 14.2.0).
    return [
        path
        for candidate_type in release_types
        if candidate_type != build_type
        for path in [build_root / f"image-{candidate_type}-{target}"]
        if path.is_dir()
    ]


def create_windows_junction(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(destination), str(source)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not create packaging image junction {destination} -> {source}: "
            f"{result.stdout}{result.stderr}"
        )


def verify_installer_tools() -> None:
    """Exercise Craft's actual embedded-7z lookup and executable tool commands."""
    from Blueprints.CraftVersion import CraftVersion
    from CraftCore import CraftCore
    from Packager.NullsoftInstallerPackager import NullsoftInstallerPackager

    makensis = CraftCore.cache.findApplication("makensis")
    archive_tool = CraftCore.cache.findApplication("7za")
    if not makensis or not archive_tool:
        raise RuntimeError("Installer tools missing: Craft must find both makensis and 7za")

    def run(executable, *arguments):
        result = subprocess.run(
            [str(executable), *arguments], capture_output=True, text=True,
            errors="replace", timeout=30, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Installer tool failed: {executable}: {result.stdout}{result.stderr}")
        return result.stdout.strip()

    version = run(makensis, "/VERSION")
    if not re.fullmatch(r"v?\d+\.\d+(?:\.\d+)?", version, re.IGNORECASE) or CraftVersion(version) < CraftVersion("3.03"):
        raise RuntimeError(f"NSIS 3.03 or newer required, found {version}")
    run(archive_tool, "i")
    with tempfile.TemporaryDirectory(prefix="p5-installer-check-") as temporary:
        # This method does not use self. Call the pinned packager's implementation
        # so a working PATH shim cannot hide a missing installer payload again.
        embedded = NullsoftInstallerPackager._prepare7Z(None, temporary)
        if embedded is None or not Path(embedded).is_file():
            raise RuntimeError("Craft NSIS could not prepare its embedded 7za.exe")
        run(embedded, "i")
    print(f"Installer tools verified: NSIS {version}, archive 7za, embedded 7za.exe.")


def prepare(craft_root: Path, package_name: str, *, dependencies_only: bool = False,
            check_installer_tools: bool = False) -> int:
    craft_root = craft_root.resolve()
    craft_bin = craft_root / "craft" / "bin"
    if not craft_bin.is_dir():
        raise RuntimeError(f"Craft bin directory not found: {craft_bin}")
    settings = craft_root / "etc" / "CraftSettings.ini"
    if not settings.is_file():
        raise RuntimeError(f"Craft settings not found: {settings}")
    if not (craft_bin.parent / "craftenv.ps1").is_file():
        raise RuntimeError(f"Craft environment entry point not found: {craft_bin.parent}")
    # CraftConfig locates itself via `craftRoot` (the Craft checkout) or
    # sys.argv[0]. CRAFT_ROOT and KDEROOT do not control this lookup. This
    # script lives outside Craft, so set its supported locator before imports.
    os.environ["craftRoot"] = str(craft_bin.parent)
    sys.path.insert(0, str(craft_bin))

    from Blueprints.CraftDependencyPackage import CraftDependencyPackage, DependencyType
    from Blueprints.CraftPackageObject import CraftPackageObject
    from Package.SourceOnlyPackageBase import SourceOnlyPackageBase
    from Package.BinaryPackageBase import BinaryPackageBase

    package = CraftPackageObject.get(package_name)
    if package is None:
        raise RuntimeError(f"Craft package not found: {package_name}")

    owner = package.instance
    dependencies = CraftDependencyPackage(package).getDependencies(
        depType=DependencyType.Runtime | DependencyType.Packaging,
        ignoredPackages=owner.ignoredPackages,
    )
    dependencies = list(dependencies)
    seven_zip = None
    seven_zip_payload = None
    if check_installer_tools:
        from CraftCompiler import CraftCompiler
        from CraftCore import CraftCore

        # NSIS reads this tool directly; it is absent from the app's runtime /
        # packaging graph. Do not add developer tools to the shipped payload.
        seven_zip = CraftPackageObject.get("dev-utils/7zip-base")
        if seven_zip is None:
            raise RuntimeError("Craft installer dependency not found: dev-utils/7zip-base")
        if all(dep.path != seven_zip.path for dep in dependencies):
            dependencies.append(seven_zip)
        seven_zip_payload = Path("dev-utils/7z") / (
            "x64/7za.exe" if CraftCore.compiler.architecture == CraftCompiler.Architecture.x86_64
            else "7za.exe"
        )

    repairs = []
    missing = []
    for dependency in dependencies:
        if dependencies_only and dependency.path == package.path:
            continue
        instance = dependency.instance
        if isinstance(instance, SourceOnlyPackageBase):
            continue

        desired = Path(instance.imageDir())
        if desired.is_dir():
            if seven_zip is not None and dependency.path == seven_zip.path:
                if not (desired / seven_zip_payload).is_file():
                    missing.append((str(dependency), str(desired / seven_zip_payload)))
            continue

        # Bootstrap installs runtime, SnoreToast and 7zip-base under MinSizeRel
        # (Builds #51/#60/#61). Both binary tool recipes copy the same upstream
        # archive for every release build type; never substitute another target.
        # Do not extend this exception to source-built Qt or the application.
        compatible_package = dependency.path == "libs/runtime" or (
            dependency.path in {"dev-utils/snoretoast", "dev-utils/7zip-base"}
            and isinstance(instance, BinaryPackageBase)
        )
        candidates = (
            compatible_image_candidates(desired.parent, desired.name)
            if compatible_package
            else []
        )
        if seven_zip is not None and dependency.path == seven_zip.path:
            candidates = [path for path in candidates if (path / seven_zip_payload).is_file()]
        if not candidates:
            missing.append((str(dependency), str(desired)))
            continue

        source = candidates[0]
        repairs.append((dependency, source, desired))

    if missing:
        details = "\n".join(f"- {name}: {path}" for name, path in missing)
        raise RuntimeError(
            "Packaging dependencies are missing Craft image directories and no compatible "
            f"image exists:\n{details}"
        )

    # Validate the complete package before creating any junctions.
    for dependency, source, desired in repairs:
        print(f"Packaging image compatibility: {dependency}: {desired.name} -> {source.name}")
        create_windows_junction(source, desired)

    if check_installer_tools:
        verify_installer_tools()
    print(f"Packaging image preparation complete; repaired {len(repairs)} image path(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--craft-root",
        type=Path,
        default=Path(os.environ.get("CRAFT_ROOT", r"C:\CraftRoot")),
    )
    parser.add_argument("--package", default="kde/kdemultimedia/editaja")
    parser.add_argument("--dependencies-only", action="store_true",
                        help="Check dependencies before compiling; full packaging check must follow the build.")
    parser.add_argument("--check-installer-tools", action="store_true",
                        help="Validate NSIS and both archive/embedded 7-Zip tools.")
    args = parser.parse_args()
    return prepare(args.craft_root.resolve(), args.package, dependencies_only=args.dependencies_only,
                   check_installer_tools=args.check_installer_tools)


if __name__ == "__main__":
    raise SystemExit(main())

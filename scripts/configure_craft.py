#!/usr/bin/env python3
"""Configure Craft's MinGW build and Qt short paths without regex replacement."""

import argparse
import configparser
from pathlib import Path


def configure(path: Path) -> None:
    config = configparser.ConfigParser(interpolation=None)
    # Do not silently create a new configuration if bootstrap failed.
    with path.open(encoding="utf-8-sig") as source:
        config.read_file(source)
    settings = {
        "General": {"ABI": "windows-gcc-x86_64"},
        "Compile": {
            "BuildType": "RelWithDebInfo",
            "UseNinja": "True",
            "MakeProgram": "mingw32-make",
        },
        # Craft itself creates/removes the subst mapping when Qt needs it.
        "ShortPath": {"DriveLetter": "Z:/"},
        "Packager": {"UseCache": "True"},
    }
    for section, values in settings.items():
        if not config.has_section(section):
            config.add_section(section)
        for key, value in values.items():
            config.set(section, key, value)
    with path.open("w", encoding="utf-8", newline="\n") as target:
        config.write(target)
    print("Craft configured: MinGW x64, RelWithDebInfo, binary cache, Qt short drive Z:/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("settings", type=Path)
    configure(parser.parse_args().settings)

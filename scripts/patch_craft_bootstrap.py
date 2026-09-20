#!/usr/bin/env python3
"""Make the pinned Craft bootstrap choose MinGW x64 non-interactively."""

import argparse
from pathlib import Path


NEEDLE = '            ("msvc2022", "cl"),\n            returnDefaultWithoutPrompt=args.use_defaults,'
REPLACEMENT = '            (None, "gcc"),\n            returnDefaultWithoutPrompt=args.use_defaults,'


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if REPLACEMENT in text:
        print("Craft bootstrap MinGW default is already patched.")
        return
    if NEEDLE not in text:
        raise SystemExit("Could not locate Craft Windows compiler default in pinned bootstrap.")
    path.write_text(text.replace(NEEDLE, REPLACEMENT, 1), encoding="utf-8")
    print("Patched Craft bootstrap default compiler to MinGW/GCC.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bootstrap", type=Path)
    patch(parser.parse_args().bootstrap)

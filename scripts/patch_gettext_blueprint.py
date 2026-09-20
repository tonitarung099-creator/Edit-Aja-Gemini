#!/usr/bin/env python3
"""Patch the Craft gettext blueprint for MinGW libxml2 linking."""

import argparse
from pathlib import Path


NEEDLE = (
    '            "gl_cv_libxml_use_included=no",\n'
    '        ]\n\n'
    '        if CraftCore.compiler.isMSVC():'
)
REPLACEMENT = (
    '            "gl_cv_libxml_use_included=no",\n'
    '        ]\n\n'
    '        if CraftCore.compiler.isMinGW():\n'
    '            # gettext detects external libxml2 headers but its final\n'
    '            # libgettextsrc link can omit the import library on MinGW.\n'
    '            self.subinfo.options.configure.args += ["LIBS=-lxml2"]\n\n'
    '        if CraftCore.compiler.isMSVC():'
)


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if 'LIBS=-lxml2' in text:
        print("gettext MinGW libxml2 hotfix is already present.")
        return
    if NEEDLE not in text:
        raise SystemExit("Could not locate gettext MinGW configure insertion point.")
    path.write_text(text.replace(NEEDLE, REPLACEMENT, 1), encoding="utf-8")
    print("Patched gettext MinGW libxml2 linking.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueprint", type=Path)
    patch(parser.parse_args().blueprint)

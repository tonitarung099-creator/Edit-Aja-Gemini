#!/usr/bin/env python3
"""Verify that the reconstructed P5 source contains every required integration."""

import argparse
import re
from pathlib import Path


TEXT_CHECKS = [
    ("src/main.cpp", r'i18n\("Update P5 Edit Aja"\)', "Update P5 Edit Aja branding"),
    ("src/aiassistant/aiassistantwidget.cpp", r"AI Edit JSON", "Phase 6 AI Edit JSON UI"),
    ("src/aiassistant/aiassistantwidget.cpp", r"Local Edit.*Lightweight", "Phase 12 Local Edit UI"),
    ("src/mainwindow.cpp", r"kdenlive_set_transform_keyframes", "Phase 12 native Transform keyframe tool"),
    ("src/mainwindow.cpp", r"keyframes->removeAllKeyframes\(\)", "Keyframe API compatibility fix"),
    ("src/mainwindow.cpp", r"keyframes->updateKeyframe\(", "Public keyframe value update path"),
    ("src/mainwindow.cpp", r"kdenlive_get_scene_map", "Phase 13 Scene Detection map tool"),
    ("src/aiassistant/aiassistantwidget.cpp", r"beginMacro.*Local Edit: Zoom snapshots", "Phase 13 Local Edit single-undo grouping"),
    ("src/aiassistant/aiassistantwidget.cpp", r"Local Edit History", "Phase 14 Local Edit History UI"),
    ("src/mainwindow.cpp", r"creatorLocalEditPreview", "Phase 14 Creator Workspace preview control"),
    ("src/aiassistant/aiassistantwidget.cpp", r"Film Context", "Phase 15 Film Context optional UI"),
    ("src/aiassistant/aiassistantwidget.cpp", r"movie_search", "Phase 15 Film Context agent tools"),
    ("src/aiassistant/aiassistantwidget.cpp", r"Build Visual Index \(Optional\)", "Phase 15 optional visual index UI"),
    ("src/aiassistant/openaicompatibleagent.cpp", r"agent_image_paths", "Phase 15 multi-keyframe vision handoff"),
    ("src/mainwindow.cpp", r"const bool outputExists = output\.exists\(\);", "Native save target existence check"),
    ("src/mainwindow.cpp", r"saveFileAs\(output\.absoluteFilePath\(\), outputExists && overwrite, saveCopy\)", "Native save overwrite semantics"),
    ("src/mainwindow.cpp", r'm_aiAssistantDock = addDock\(i18n\("AI Agent"\)', "AI Agent right-sidebar dock"),
    ("src/mainwindow.cpp", r"Keep AI Agent as the primary right sidebar", "AI Agent post-layout docking"),
    ("src/aiassistant/aiassistantwidget.cpp", r"aiAssistantScrollArea", "Scrollable AI Agent sidebar"),
    ("src/aiassistant/aiassistantwidget.cpp", r"AI Agent — Main Control", "AI Agent primary command surface"),
]


# Creating subtitles must initialize the lazy model through the native UI path.
# Match within each dispatch branch so another tool's initializer cannot pass.
for tool in ("kdenlive_add_subtitle", "kdenlive_import_subtitles", "kdenlive_add_subtitle_batch"):
    TEXT_CHECKS.append((
        "src/mainwindow.cpp",
        rf'if \(toolName == QLatin1String\("{tool}"\)\) \{{\s*'
        r'//[^\n]*\n\s*showSubtitleTrack\(\);\s*const auto subtitles = model->getSubtitleModel\(\);',
        f"Native subtitle initialization for {tool}",
    ))

REQUIRED_FILES = [
    ("src/aiassistant/aiassistantwidget.cpp", "Phase 5 AI assistant source"),
    ("data/scripts/filmcontext/film_context.py", "Phase 15 local Film Context backend"),
]


def verify(root: Path) -> None:
    failures = []

    for relative, label in REQUIRED_FILES:
        if not (root / relative).is_file():
            failures.append(f"{label} is missing: {relative}")

    for relative, pattern, label in TEXT_CHECKS:
        path = root / relative
        if not path.is_file():
            failures.append(f"{label} cannot be checked because {relative} is missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not re.search(pattern, text, flags=re.MULTILINE):
            failures.append(f"{label} verification failed in {relative}")

    if failures:
        raise SystemExit("\n".join(failures))

    print(f"Verified {len(TEXT_CHECKS)} source markers and {len(REQUIRED_FILES)} required files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    verify(parser.parse_args().source_root.resolve())

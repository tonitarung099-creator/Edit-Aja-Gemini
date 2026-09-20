# Update P5 Edit Aja

**Update P5 Edit Aja** is the experimental, expanded version of the Edit Aja video editor. It starts from the complete Edit Aja Phase 5 baseline built on Kdenlive/MLT, while the original `Edit-Aja` repository can remain stable.

The project is designed around four editing paths that share the same native timeline foundation:

1. normal manual editing,
2. the lightweight offline-first **Local Edit Agent** for everyday natural-language timeline commands,
3. the existing Phase 5 built-in AI Agent / MCP / REST control layer for heavier AI/tool use, and
4. deterministic **AI Edit JSON** files created outside the editor (for example by ChatGPT) and applied to the editable timeline.

## Current baseline

The repository retains the complete Phase 1–5 Edit Aja work:

- built-in OpenAI-compatible API agent,
- MCP and localhost REST/JSON bridges,
- shared native `kdenlive_*` editing tool registry,
- project/timeline/media/effect/subtitle/render tools,
- local transcription and silence/jump-cut primitives,
- Edit Aja branding and Windows packaging workflow.

The internal `kdenlive_*` names intentionally remain for Phase 5 API compatibility.

## Phase 6: AI Edit JSON

The first Update P5 feature is implemented both as developer tooling under `tools/ai_edit/` / `ai-edit/` and as a native editor UI applied by the Phase 6 source patch.

A JSON edit file can call the existing Phase 5 registry directly, reference values returned by earlier steps, resolve a live track, or find the clip covering a timeline time. This means an external AI can make editing decisions while Update P5 Edit Aja remains the deterministic executor.

```text
MP4 + editing request
        ↓
      ChatGPT
        ↓
update-p5-ai-edit JSON
        ↓
AI Edit runner
        ↓
Phase 5 localhost REST bridge
        ↓
shared native tool registry
        ↓
editable Kdenlive/MLT timeline
```

Validate an edit file:

```text
python tools/ai_edit/update_p5_ai_edit.py validate ai-edit/examples/documentary-basic.json
```

Inside the application, use the **AI Edit JSON** button in the Creator Workspace (or the AI Assistant panel) to choose a JSON file, preview/validate it, and apply it directly to the editable timeline. Missing asset variables can be resolved with native file pickers.

For developer/automation use, with Update P5 Edit Aja running and the AI Agent panel opened, inspect the live catalog or apply a plan from the command line:

```text
python tools/ai_edit/update_p5_ai_edit.py catalog
python tools/ai_edit/update_p5_ai_edit.py apply my-edit.json
```

The runner creates a project checkpoint before applying edits by default. See `ai-edit/FORMAT.md` for the format, references, variables and selectors.


## Local Edit Agent

The Local Edit Agent is a lightweight parser/router for commands typed in ordinary Indonesian or mixed editing language. It does not run a large model for normal editing commands.

Examples:

```text
ptong 5
hpus sceen 73
split disini
semua snapshpt zom 100 ke 111 5 dtk
```

The local path performs typo normalization, timeline-context resolution, confidence checks and deterministic animation math. Complex semantic requests are routed to the existing API AI agent; external research/actions can be routed to MCP; specialized local work can be routed to whisper.cpp, DeepFilterNet, Demucs, SAM 2 and the other installed engines.

For the snapshot zoom example, 100% to 111% over 5 seconds means a 4.5-second snapshot ends at 109.9%; clips longer than 5 seconds reach 111% at 5 seconds and then hold. See `docs/features/LOCAL_EDIT_AGENT.md`.

Phase 12 also adds a native **Local Edit** command bar in the Creator Workspace / AI Assistant. Deterministic commands inspect the live timeline and execute through the same native registry. Smooth snapshot zoom uses the editable `kdenlive_set_transform_keyframes` tool rather than cutting an image into fake animation segments. Complex commands are handed off to the existing API/MCP path without being sent automatically.


## Film Context (optional)

Film Context is an optional **local movie retrieval layer** for AI agents. It does not edit the timeline and it does not replace AI Edit JSON. Its job is to let an API model search a long movie without uploading or re-reading the whole movie.

The base index uses FFmpeg/FFprobe, SQLite, scene timestamps and optional SRT dialogue. Search results are deliberately compact. Neighbor context and JPEG keyframes are fetched only when requested, so an agent can escalate from text metadata to a few candidate images instead of sending the full film.

Stable tool names are: `movie_context_status`, `movie_search`, `movie_get_scene`, `movie_get_context`, and `movie_get_keyframes`. The existing AI Assistant gets an optional Film Context section that is disabled by default; when enabled, it can build/select an index and use these tools without changing the ChatGPT/AI Edit JSON path. An additional OpenCLIP backend can optionally tag one representative frame per scene once and cache bilingual visual tags; OpenCLIP/PyTorch are not required by the base editor. See `docs/features/FILM_CONTEXT.md`.

## New intelligence engines

Update P5 now includes feature engines outside the original Phase 5 AI Agent:

- **Media Intelligence** — FFprobe metadata, silence detection, scene/shot detection, black-frame detection, loudness measurement, pacing analysis, and smart jump-cut JSON generation.
- **Caption Intelligence** — SRT/transcript ingestion, phrase captions, word-by-word captions, timing resegmentation, case transforms, and direct native subtitle-batch JSON generation.
- **Audio Intelligence** — LUFS/true-peak measurement, safety-bounded gain recommendations, native clip-volume normalization, and optional native audio fades.
- **Dialogue Intelligence** — filler-word, immediate-repeat and long-gap analysis with conservative native ripple-cut plans.
- **Visual Intelligence** — normalized subject tracks, optional OpenCV face tracking, and editable smart reframe plans for vertical/square/portrait/landscape output.
- **Documentary Toolkit** — B-roll insertion/placeholders, lower thirds, chapter cards, quote cards and segmented Ken Burns photo motion.
- **Optional local backends** — whisper.cpp transcription and DeepFilterNet voice cleanup, kept outside the base install.

These engines intentionally feed the same Phase 6 AI Edit/native tool layer rather than introducing another AI agent.

## Documentation

Feature documentation is indexed in `docs/features/README.md`. Build and debugging instructions live in `BUILDING.md`. AI/developer engineering behavior is governed by `AGENTS.md` and the detailed evidence-first rules in `docs/AI_WORKING_RULES.md`; a standalone copy/paste prompt is available at `docs/ai/PROMPT_AI_TECHNICAL_LEAD_V2_EDIT_AJA.txt`.

## Roadmap

See `ROADMAP.md`. Planned areas now move beyond the completed native AI Edit import UI into richer change previews, scene/media intelligence, advanced captions and audio cleanup, object tracking/masking/background removal, smart reframe, documentary graphics, and optional analysis/model backends.

## Upstream and license

Update P5 Edit Aja is based on Edit Aja and Kdenlive and preserves the GPL licensing and upstream copyright notices. The reproducible build remains pinned to upstream Kdenlive commit:

`c3d8a38c04470f6726b21485fc488f2cd2921654`

Upstream Kdenlive: https://github.com/KDE/kdenlive

Original baseline repository: https://github.com/tonitarung099-creator/Edit-Aja

This repository: https://github.com/tonitarung099-creator/Update-P5-Edit-Aja

Third-party engines/models added in later phases must receive a separate license/dependency review before they are bundled or distributed.

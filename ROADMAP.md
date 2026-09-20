# Update P5 Edit Aja roadmap

`Update P5 Edit Aja` starts from the full Edit Aja Phase 5 baseline and develops the more experimental automation/AI-native feature set here, without changing the original Edit Aja repository.

## Phase 6 — AI Edit JSON

- [x] Deterministic JSON edit-script format.
- [x] Phase 5 REST discovery/auth client.
- [x] Live tool-catalog validation.
- [x] Cross-step `$ref` values.
- [x] Portable `$var` values and relative media paths.
- [x] Live `$track` and `$clip_at` selectors.
- [x] Automatic project checkpoint before apply.
- [x] Execution report and stop/continue-on-error modes.
- [x] Unit tests and CI.
- [x] Native **AI Edit JSON** import UI inside the editor.
- [ ] Rich visual change preview and per-step enable/disable UI (current preview validates and summarizes the plan).
- [x] One-click open/validate/apply flow for JSON produced by ChatGPT.

## Phase 7 — Media intelligence

Planned as optional analysis backends feeding the same edit-script/native tool layer:

- [x] scene/shot detection using FFmpeg scene scores (optional PySceneDetect backend can be added later),
- [x] silence/pause analysis and smart jump-cut JSON generation,
- [x] motion/activity analysis,
- [x] filler-word, immediate-repeat and long-gap dialogue analysis,
- [x] conservative semantic bad-take detection/review with explicit approval before removal,
- [x] pacing analysis from detected scene durations,
- [x] beat analysis and native beat-synced cut planning.
- [x] beat-synced Smart Montage builder.
- [x] black-frame detection.
- [x] media metadata normalization with FFprobe.

## Phase 8 — Speech, captions and audio

- [x] optional local whisper.cpp backend alongside existing speech recognition,
- [x] phrase and word-level smart caption segmentation with reusable native subtitle styles,
- [x] editable animated word/title caption presets (clean/pop/punch/bounce),
- [x] speaker-aware transcript/caption workflow,
- [x] optional DeepFilterNet voice cleanup/noise suppression backend,
- [x] optional Demucs vocal/music/stem separation backend,
- [x] LUFS/true-peak analysis and native clip-gain normalization plans,
- [x] native fade-in/fade-out plan generation,
- [x] native music auto-ducking under speech.

## Phase 9 — Visual intelligence

- [x] normalized subject-track interchange format,
- [x] optional OpenCV face tracking backend,
- [x] optional SAM 2/SAM 2.1 video object segmentation/tracking backend,
- [x] portable mask-track format and subject isolation,
- [x] transparent foreground, background blur, object blur and background replacement,
- [x] smart reframe planner for vertical, square, portrait and landscape outputs,
- [x] optional SAM 2-style segmentation backend.

GPU-heavy models should remain optional modules rather than mandatory editor dependencies.

## Phase 10 — Documentary/creator graphics

- [x] B-roll insertion and placeholders/asset slots,
- [x] map/timeline/bar/line SVG graphics,
- [x] quote/source cards and lower thirds,
- [x] chapter cards,
- [x] editable Ken Burns/photo motion presets,
- [x] reusable staged documentary motion-graphics templates.
- [x] beat-synced B-roll / AI-image Smart Montage.

- [x] transcript-driven B-roll planning with prompt hints, placeholders and asset resolution.
- [x] multi-stage Creator Pipeline with artifact passing and final AI Edit composition.

## Interchange and architecture

- Keep Kdenlive/MLT as the native editable timeline/rendering foundation.
- Keep the existing Phase 5 built-in AI Agent unchanged as one control path.
- AI Edit JSON is a second deterministic control path using the same native registry.
- Continue using OpenTimelineIO support where suitable for editorial interchange.
- External analysis/model integrations must be isolated behind adapters and reviewed for code/model licensing before distribution.

## Phase 11 — Creator workflows

- [x] Highlight/social-clip candidate intelligence with reviewable extraction plans.
- [x] Creator Pipeline orchestration with named artifact passing and final AI Edit composition.
- [x] Workflow presets for documentary, talking-head, podcast and shorts.
- [x] AI Asset Manifest for GPT Images/video generation handoff and asset resolution.
- [ ] Rich native Creator Workspace UI for configuring and running these workflows.
- [ ] Per-stage progress/cancel controls and visual artifact browser.


## Phase 12 — Lightweight Local Edit Agent

- [x] Offline-first natural-language command interpreter with no LLM required for normal commands.
- [x] Indonesian/English shorthand plus conservative fuzzy typo correction and user alias dictionary.
- [x] Timeline-aware intent model for playhead, selected clip, scene indexes and snapshot collections.
- [x] Deterministic split/delete intent parsing with confidence and confirmation metadata.
- [x] Animation math engine for proportional snapshot zoom (for example 100% to 111% at 5 seconds; a 4.5-second snapshot ends at 109.9%).
- [x] Long snapshot behavior: reach target at the requested time, then hold.
- [x] Command routing: LOCAL / LOCAL_TOOL / AI / MCP.
- [x] Route specialized local work to existing engines instead of a general local LLM.
- [x] Unit tests and CI.
- [x] Native Local Edit command bar in the Creator/Filmora-like workspace and AI Assistant.
- [x] Native timeline context adapter for selection, playhead, tracks and ordered visual clips.
- [x] Dedicated `kdenlive_set_transform_keyframes` native tool for editable smooth/linear zoom animation.
- [x] Direct execution adapter from native Local Edit intent to the shared native tool registry.
- [x] Scene Detection marker map integration for `scene N`, with source-to-timeline range mapping and ordered-clip fallback.
- [x] Single-undo grouping for multi-snapshot Local Edit zoom jobs.
- [x] Session command history and visual interpretation preview with separate Preview/Apply controls.


## Phase 15 — Optional Film Context

- [x] Keep Film Context separate from AI Edit JSON and timeline execution.
- [x] Local FFmpeg scene/shot indexing with SQLite cache.
- [x] Optional SRT/dialogue ingestion mapped to scene time ranges.
- [x] Compact local BM25 scene retrieval with optional continuity bias.
- [x] Neighbor-context lookup without exposing the entire film.
- [x] On-demand keyframe extraction only for requested candidate scenes.
- [x] Stable JSON tool protocol for Gemini/API adapters.
- [x] Scene annotation field so later local semantic/vision backends can enrich the same index without changing the protocol.
- [x] Native AI Assistant panel for selecting/building a Film Context index.
- [x] Direct built-in AI Agent bridge to the Film Context tool protocol.
- [x] Optional OpenCLIP semantic visual tagging with bilingual Indonesian/English cached tags; heavy dependencies remain unbundled.
- [ ] Richer free-form vector retrieval backend after model/dependency review.
- [x] Text-first vision escalation to a few requested keyframes, capped at six images per tool call when vision attachment is enabled.
- [ ] Short-clip motion escalation only when still frames are insufficient.

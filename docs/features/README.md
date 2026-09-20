# Feature documentation

Feature-specific design notes live here so the repository root stays focused on
the project entry points, build instructions, roadmap, and licensing.

| Area | Documents |
| --- | --- |
| AI control and orchestration | [Capability Registry](CAPABILITY_REGISTRY.md), [Creator Pipeline](CREATOR_PIPELINE.md), [Workflow Presets](WORKFLOW_PRESETS.md), [AI Asset Manifest](AI_ASSET_MANIFEST.md), [Local Edit Agent](LOCAL_EDIT_AGENT.md), [Film Context](FILM_CONTEXT.md) |
| Media and editorial intelligence | [Media Intelligence](MEDIA_INTELLIGENCE.md), [Dialogue Intelligence](DIALOGUE_INTELLIGENCE.md), [Bad Take Review](BAD_TAKE_REVIEW.md), [Beat Sync](BEAT_SYNC.md), [Rhythm Intelligence](RHYTHM_INTELLIGENCE.md), [Smart Montage](SMART_MONTAGE.md), [Highlight Intelligence](HIGHLIGHT_INTELLIGENCE.md), [B-roll Planner](BROLL_PLANNER.md) |
| Audio and speech | [Audio Intelligence](AUDIO_INTELLIGENCE.md), [Audio Backends](AUDIO_BACKENDS.md), [Speech Backends](SPEECH_BACKENDS.md), [Demucs Backend](DEMUCS_BACKEND.md), [Auto Ducking](AUTO_DUCKING.md) |
| Captions | [Caption Intelligence](CAPTION_INTELLIGENCE.md), [Animated Captions](ANIMATED_CAPTIONS.md), [Speaker Captions](SPEAKER_CAPTIONS.md) |
| Visual and segmentation | [Visual Intelligence](VISUAL_INTELLIGENCE.md), [Segmentation Backends](SEGMENTATION_BACKENDS.md), [Mask Effects](MASK_EFFECTS.md) |
| Documentary graphics | [Documentary Toolkit](DOCUMENTARY_TOOLKIT.md), [Documentary Graphics](DOCUMENTARY_GRAPHICS.md), [Motion Graphics Templates](MOTION_GRAPHICS_TEMPLATES.md) |

## Repository-level documents

Keep only cross-cutting entry points at the repository root:

- `README.md` — project overview and main navigation.
- `BUILDING.md` — reproducible Windows build and debugging.
- `ROADMAP.md` — phase status and planned work.
- `COPYING` and `LICENSE-NOTE.md` — licensing information.

New feature documentation should be added here instead of the repository root.

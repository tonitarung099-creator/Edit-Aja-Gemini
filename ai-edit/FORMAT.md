# Update P5 AI Edit JSON v1

This format is a deterministic editing script for **Update P5 Edit Aja**. It is separate from the built-in AI Agent: ChatGPT or another AI can create the JSON outside the editor, while the local runner executes it through the existing Phase 5 localhost REST bridge and shared native tool registry.

## Why this format

- It can call every current/future `kdenlive_*` registry tool instead of hard-coding a small subset of edits.
- It supports references to results from earlier steps, so imported media and newly-created tracks/clips can be used without knowing numeric IDs in advance.
- It supports live selectors such as `$clip_at`, so an edit can target the clip covering a specific time after previous operations have changed the timeline.
- It validates the required tools against the running editor before applying anything.
- It creates a project checkpoint by default.

## Minimal file

```json
{
  "format": "update-p5-ai-edit",
  "version": 1,
  "steps": [
    {
      "id": "timeline",
      "tool": "kdenlive_get_timeline_state",
      "arguments": {"include_items": true}
    }
  ]
}
```

## Variables

Define portable values in `variables` and reference them with `$var`:

```json
"variables": {"MAIN_VIDEO": "./input.mp4"},
"arguments": {"path": {"$var": "MAIN_VIDEO"}}
```

CLI values override values stored in the JSON:

```text
python tools/ai_edit/update_p5_ai_edit.py apply edit.json --var MAIN_VIDEO=D:\\Video\\input.mp4
```

Relative file paths are resolved relative to the JSON file.

## References between steps

The complete REST response for every executed step is stored under its `id`. Read values with `$ref`:

```json
{
  "id": "import-main",
  "tool": "kdenlive_import_media",
  "arguments": {"path": {"$var": "MAIN_VIDEO"}}
},
{
  "id": "insert-main",
  "tool": "kdenlive_insert_bin_clip",
  "arguments": {
    "bin_id": {"$ref": "import-main.result.bin_id"},
    "track_id": {"$ref": "video-track.result.track_id"},
    "position_seconds": 0
  }
}
```

## Track selector

`$track` resolves a live timeline track ID. Filters are optional and `index` is zero-based among matches.

```json
{"$track": {"audio": false, "index": 0}}
```

Supported selector keys: `id`, `audio`, `tag`, `position`, `index`.

## Clip-at-time selector

`$clip_at` resolves the unique clip covering a live timeline position:

```json
{
  "clip_id": {
    "$clip_at": {
      "track_id": {"$ref": "video-track.result.track_id"},
      "position_seconds": 12.5
    }
  },
  "scale_percent": 112
}
```

This is useful after cuts because numeric clip IDs may have changed.

## Safety and execution

The runner reads the same per-session `kdenlive-open-agent.json` discovery file used by Phase 5 MCP/REST clients. The editor must be running and the AI Agent panel must have started the local bridge.

Commands:

```text
python tools/ai_edit/update_p5_ai_edit.py validate edit.json
python tools/ai_edit/update_p5_ai_edit.py plan edit.json
python tools/ai_edit/update_p5_ai_edit.py catalog
python tools/ai_edit/update_p5_ai_edit.py apply edit.json
```

`apply` asks for the literal confirmation `APPLY` unless `--yes` is supplied. A timestamped project checkpoint is created before execution by default; use `--no-checkpoint` only when that is intentional.

## Authoring guidance for GPT

Prefer one `kdenlive_remove_ranges` step for many jump cuts because Phase 5 normalizes ranges and applies them from right to left. After ripple removals, express later decorative timing in the post-cut timeline or use live selectors such as `$clip_at`.

Use `kdenlive_get_timeline_state`, `kdenlive_list_effects`, and `kdenlive_list_transitions` before precision edits when working against an existing project. For a new project, create/import resources first and reference their returned IDs instead of guessing IDs.

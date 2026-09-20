# ChatGPT authoring guide for Update P5 AI Edit JSON

Use this contract when an external AI (including ChatGPT) creates an edit plan for **Update P5 Edit Aja**.

## Output contract

Return one JSON object using:

- `"format": "update-p5-ai-edit"`
- `"version": 1`
- stable, unique step IDs
- only `kdenlive_*` tool names available in the Update P5 tool registry
- seconds for human-facing edit timing unless exact frames are required

Do not write or modify a `.kdenlive` XML project directly. The JSON must describe editing decisions; Update P5 Edit Aja converts them into native editable timeline operations.

## Portable media variables

When ChatGPT does not know the user's local file path, leave asset variables empty:

```json
"variables": {
  "MAIN_VIDEO": "",
  "BROLL_01": ""
}
```

The native **AI Edit JSON** importer recognizes file-like variable names such as `VIDEO`, `AUDIO`, `IMAGE`, `MEDIA`, `ASSET`, `FILE`, or `PATH` and opens a file picker the first time an unresolved value is needed.

For CLI automation, pass the same values with:

```text
--var MAIN_VIDEO=D:\\Video\\main.mp4
```

## Prefer references instead of guessed IDs

Never guess track, bin, or clip IDs. Create/import first, then reference the result:

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

For an existing timeline, target a live clip by time instead of guessing its ID:

```json
"clip_id": {
  "$clip_at": {
    "position_seconds": 42.5,
    "track": {"audio": false, "index": 0}
  }
}
```

## Editing order

For edits that ripple the timeline, prefer this order:

1. create/import media and tracks,
2. perform large structural cuts,
3. re-inspect or use live selectors,
4. add B-roll/titles/effects,
5. add subtitles/audio polish,
6. save.

When removing many ranges, prefer one `kdenlive_remove_ranges` step rather than many independent cuts. Phase 5 normalizes the ranges and applies them from right to left.

## Safety

Keep this unless the user explicitly requests otherwise:

```json
"safety": {
  "checkpoint": true,
  "checkpoint_label": "before-ai-edit"
}
```

The native importer validates every required tool before applying the plan, shows a summary, asks for confirmation, and stops at the first failed step.

## Example request to ChatGPT

> Analyze this MP4 as a YouTube documentary. Remove obvious dead air, keep natural breathing room, use moderate zooms only on important statements, create subtitle segments, and return only an Update P5 AI Edit JSON plan. Do not render the video. Use empty local media variables so Update P5 Edit Aja asks me to select the files.

The AI should return the edit decision JSON, not a rendered MP4 and not Kdenlive XML.

# Local Edit Agent

Local Edit Agent is the lightweight, offline-first natural-language command path for Update P5 Edit Aja.

It is intentionally **not** a second large AI model. Simple editing language is handled deterministically on the user's laptop:

\`\`\`text
user words
  -> typo/alias normalizer
  -> local command parser
  -> timeline context
  -> math engine
  -> native tool hint / native adapter
  -> editable timeline
\`\`\`

Only requests that genuinely need semantic judgement or an external service are routed to the existing API/MCP AI path.

## Routing

The interpreter returns one of four routes:

- \`local\` — lightweight parser/math/context only.
- \`local_tool\` — specialized installed local engine such as whisper.cpp, DeepFilterNet, Demucs, SAM 2, or Media Intelligence.
- \`ai\` — semantic/editorial reasoning should go to the configured API AI agent.
- \`mcp\` — external search/assets/actions should go through an MCP-capable agent/tool.

## Typo-tolerant commands

Examples that remain local:

\`\`\`text
ptong 5
potong menit 5
hpus sceen 73
split disini
semua snapshpt zom 100 ke 111 5 dtk
\`\`\`

\`ptong 5\` is normalized to \`potong 5\`. By user convention a bare number after split/cut is treated as minutes, but is marked \`needs_confirmation=true\` so the UI can show:

\`\`\`text
Dipahami sebagai: Potong di 05:00
[ Jalankan ] [ Ubah ]
\`\`\`

Explicit \`potong menit 5\` is high-confidence and does not require that clarification.

## Timeline context

The parser can receive a small JSON context object, for example:

\`\`\`json
{
  "playhead_seconds": 123.4,
  "selected_clip_id": 42,
  "selected_clip_duration": 4.5,
  "scenes": {
    "73": {"start": 501.4, "end": 507.9}
  },
  "snapshots": [
    {"id": 1001, "duration": 4.5},
    {"id": 1002, "duration": 8.0}
  ]
}
\`\`\`

This lets phrases such as \`split disini\`, \`hapus scene 73\`, and \`zoom snapshot ini\` resolve without an LLM.

## Zoom math

For:

\`\`\`text
semua snapshot zoom 100 ke 111 5 detik
\`\`\`

the reference motion is 100% at time 0 and 111% at 5 seconds.

For a snapshot that is only 4.5 seconds:

\`\`\`text
100 + (111 - 100) * (4.5 / 5) = 109.9%
\`\`\`

So its generated animation ends at 109.9%. A snapshot longer than 5 seconds reaches 111% at 5 seconds, then holds 111% for the rest of the clip. Snapshot/photo animation defaults to smooth easing.

The interpreter emits explicit keyframe math as portable command IR. Phase 12 adds the native `kdenlive_set_transform_keyframes` executor, which writes editable qtblend/Transform keyframes and supports smooth or linear scale animation, proportional short-clip endpoints, and target-then-hold behavior.

## CLI

\`\`\`bash
python tools/local_edit_agent/local_edit_agent.py ptong 5 --pretty
python tools/local_edit_agent/local_edit_agent.py "hpus sceen 73" --context timeline-context.json --pretty
python tools/local_edit_agent/local_edit_agent.py "semua snapshpt zom 100 ke 111 5 dtk" --context timeline-context.json --pretty
\`\`\`

No third-party Python package is required for the normal parser.

## Safety/UX rule

High-confidence deterministic commands may be configured for direct execution. Ambiguous or destructive commands should show the normalized interpretation first. Unknown language never guesses a native edit: it routes to the configured AI/MCP path instead.


## Native command bar

Phase 12 adds a **Local Edit** command field directly to the Creator Workspace toolbar and to the AI Assistant panel. The native command path reads the live timeline state and executes safe deterministic commands through the same shared native registry.

Examples:

```text
ptong 5
potong menit 5
split disini
hpus sceen 73
semua snapshot zoom 100 ke 111 5 detik
```

For complex semantic language, the command is placed into the existing API AI Agent prompt but is **not sent automatically**. External-search wording routes to MCP; specialized local work routes to the relevant local engine.

`scene N` now prefers Kdenlive Scene Detection markers through `kdenlive_get_scene_map`; ordered visual clips are only the fallback when no detected scene markers are available.


## Scene numbering

When the user types `hapus scene 73`, Local Edit now first asks the native `kdenlive_get_scene_map` tool for Kdenlive Scene Detection markers named `Scene N`.

- Range markers map directly to detected source scene ranges.
- Point markers are treated as **cut boundaries**: Scene 1 is source start -> first cut, Scene 2 is first cut -> second cut, and a final synthetic scene is added from the last cut to source end.
- Source ranges are mapped through the timeline clip's source in/out and speed.
- If no Scene Detection markers exist, Local Edit falls back to ordered visual clips so already-cut timelines still work.

Deleting a detected scene uses `kdenlive_remove_ranges`, so unlocked timeline tracks ripple together through that scene range.

## Undo grouping

A Local Edit command that applies the same zoom to multiple snapshots is wrapped in a Kdenlive undo macro. The whole job therefore appears as one logical undo operation instead of one Ctrl+Z per snapshot.


## Preview and History

Phase 14 separates understanding from execution:

```text
type command
  -> Preview
  -> inspect what Edit Aja understood
  -> Apply
  -> timeline changes
```

Pressing **Enter** in the Creator Workspace Local Edit field runs Preview, not Apply. The preview can show the resolved cut time, detected scene range, number of affected snapshots, start/target zoom, proportional short-clip endpoint and whether the job is grouped into one Undo.

The AI Assistant panel also keeps a session **Local Edit History** with time, route, original command and outcome. Commands executed from the Creator Workspace toolbar use the same executor, so they appear in the same history.

Previewing an AI/MCP command does not send anything and does not even populate/submit the external agent. Apply may place the command into the existing AI Agent prompt, where the user can review it before any API call.

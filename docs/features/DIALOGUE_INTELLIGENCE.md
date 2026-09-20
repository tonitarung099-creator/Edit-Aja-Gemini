# Dialogue Intelligence

Dialogue Intelligence cleans talking-head, podcast and narration edits from **word-level timestamps**.

It currently detects:

- filler words such as `um`, `uh`, `hmm`, `eee`, `eh`, and `anu`,
- immediately repeated words,
- long gaps between words.

It can emit either a review report or a conservative Phase 6 ripple-cut plan.

## Analyze transcript

Use the normalized transcript produced by the optional whisper.cpp backend:

```text
python tools/dialogue_intelligence/dialogue_intelligence.py transcript.json \
  --format report \
  --output dialogue-report.json
```

## Generate cleanup edit

```text
python tools/dialogue_intelligence/dialogue_intelligence.py transcript.json \
  --format ai-edit \
  --shorten-gaps \
  --gap-keep 0.35 \
  --output dialogue-cleanup.edit.json
```

By default it removes detected filler words and immediate repeated words from the first video and audio tracks together. The generated file uses `kdenlive_remove_ranges`, so cuts are native, ripple-aware and checkpointed by Phase 6.

Additional filler words can be supplied repeatedly with `--filler WORD`.

For safety, "bad take" semantic removal is not guessed automatically. A later model-assisted reviewer can add ranges after reviewing transcript context, while this deterministic layer handles the obvious mechanical cleanup.

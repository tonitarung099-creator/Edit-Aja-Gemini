# Highlight Intelligence

Highlight Intelligence finds **reviewable social/short-form clip candidates** from timestamped transcripts.

It scores candidate windows using deterministic signals such as:

- hook/question language,
- contrast or surprise phrasing,
- numbers/dates,
- information density,
- fit to a target duration.

## Scan

```text
python tools/highlight_intelligence/highlight_intelligence.py scan transcript.json \
  --min-duration 20 \
  --target-duration 35 \
  --max-duration 60 \
  --output highlights.json
```

The result contains ranked, mostly non-overlapping candidates with transcript text, timestamps, score and reasons.

## Compile one approved highlight

```text
python tools/highlight_intelligence/highlight_intelligence.py compile \
  highlights.json highlight-001 \
  --output highlight.edit.json
```

The resulting native plan removes timeline material before and after the approved highlight from the selected video/audio tracks. Combine this plan with Smart Reframe and Animated Captions to build a 9:16 short-form workflow.

Candidate scoring is a review aid rather than an LLM judgment; the selected highlight remains a user/GPT decision.

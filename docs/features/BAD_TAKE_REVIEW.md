# Bad Take Review

Bad Take Review identifies **likely retakes/corrections** from a timestamped transcript while deliberately avoiding automatic destructive editing.

It looks for deterministic signals such as:

- correction language: `maksud saya`, `bukan`, `ralat`, `sorry`,
- explicit retry language: `ulang lagi`, `take lagi`,
- short filler-heavy false starts,
- nearby repeated phrase prefixes,
- short starts followed by a fuller version of the same sentence.

## Scan

```text
python tools/bad_take_review/bad_take_review.py scan transcript.json \
  --output bad-take-review.json
```

Each candidate has an ID, timestamp range, reasons and a confidence score.

## Approve explicitly

Create a small approvals file:

```json
{"approved":["candidate-0001","candidate-0003"]}
```

Then compile only those approved ranges:

```text
python tools/bad_take_review/bad_take_review.py compile \
  bad-take-review.json approvals.json \
  --output bad-takes.edit.json
```

The resulting Phase 6 plan removes only the approved ranges from the selected video/audio tracks. This keeps semantic removal reviewable instead of letting heuristics silently delete speech.

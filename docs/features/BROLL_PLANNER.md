# Transcript B-roll Planner

B-roll Planner turns narration transcripts into structured visual slots.

For each selected narration segment it produces:

- timeline start/end,
- visual type,
- why that visual type was chosen,
- a prompt hint for GPT Images/video generation,
- an empty asset field that can later be resolved.

Current visual categories include:

- historical map,
- archive/history visual,
- data graphic,
- map/establishing shot,
- portrait/archive person,
- process diagram,
- quote card,
- general illustrative B-roll.

## Build a B-roll plan

```text
python tools/broll_planner/broll_planner.py plan transcript.json \
  --minimum-gap 3 \
  --default-duration 4 \
  --output broll-plan.json
```

## Put placeholders on the timeline

```text
python tools/broll_planner/broll_planner.py placeholders broll-plan.json \
  --output broll-placeholders.edit.json
```

This creates editable title clips showing what should eventually appear.

## Resolve final assets

Create a slot-to-file mapping:

```json
{
  "broll-0001":"./visuals/map-japan.jpg",
  "broll-0002":"./visuals/meiji.mp4"
}
```

Then:

```text
python tools/broll_planner/broll_planner.py assets \
  broll-plan.json examples/documentary/broll-assets.json \
  --output broll-assets.edit.json
```

The final plan imports, inserts and resizes the real assets natively. The planner does not require an LLM; ChatGPT can enrich the prompt hints or choose better visuals without changing the interchange format.

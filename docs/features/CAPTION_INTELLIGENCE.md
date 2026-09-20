# Smart Caption Intelligence

Update P5 can turn an SRT file or timestamped transcript JSON into cleaner creator-style captions **before** importing them into the timeline.

Implemented modes:

- **phrase** — short readable captions split by word count, character count and duration,
- **word** — one word at a time for fast short-form/TikTok-style captions,
- case transforms: keep, uppercase, lowercase or title case,
- SRT output,
- normalized JSON output,
- direct Phase 6 AI Edit JSON output using `kdenlive_add_subtitle_batch`,
- Kdenlive subtitle style/layer selection.

## Phrase captions

```text
python tools/caption_intelligence/caption_intelligence.py transcript.json \
  --mode phrase \
  --max-words 5 \
  --max-chars 32 \
  --max-duration 2.2 \
  --format ai-edit \
  --output captions.json
```

Then open `captions.json` with the Phase 6 AI Edit importer.

## Word-by-word captions

```text
python tools/caption_intelligence/caption_intelligence.py subtitles.srt \
  --mode word \
  --case upper \
  --format ai-edit \
  --output word-captions.json
```

The current implementation uses native Kdenlive subtitles. More elaborate animated typography remains a later motion-graphics layer; the important part here is that timing and segmentation are already deterministic and editable.

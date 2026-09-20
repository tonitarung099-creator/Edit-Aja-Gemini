# Optional Demucs Stem Separation Backend

Update P5 can use **Demucs** as an optional local audio source-separation backend.

Demucs is not bundled with the base editor. Install it in a separate Python environment, then run the adapter against a media file.

Supported workflows include:

- four-stem separation: vocals, drums, bass, other,
- two-stem separation such as vocals + no_vocals,
- CPU or GPU device selection,
- optional custom model selection,
- native Phase 6 plan generation.

## Example: vocals + accompaniment

```text
python tools/audio_backends/demucs.py song.mp3 \
  --two-stems vocals \
  --output-dir ./stems \
  --plan-output stems.edit.json
```

The adapter copies generated stems into stable filenames, then the optional edit plan:

- creates one native audio track per stem,
- imports each stem,
- inserts them at the requested timeline time,
- optionally mutes the original audio clip.

Demucs upstream uses the MIT license. Model/dependency distribution should still be audited before bundling; Update P5 therefore keeps this backend optional.

# Speaker-aware Captions

Speaker Captions converts diarized/interview transcripts into separate native subtitle batches per speaker.

It understands:

- explicit `speaker` labels,
- whisper.cpp/tinydiarize-style `speaker_turn_next`,
- custom Kdenlive subtitle style per speaker,
- custom subtitle layer per speaker.

## Example

```text
python tools/speaker_captions/speaker_captions.py transcript.json \
  --styles examples/caption/speaker-styles.json \
  --output interview-captions.edit.json
```

A style config maps speaker names to Kdenlive subtitle style/layer:

```json
{
  "Speaker 1": {"style":"Default","layer":0},
  "Speaker 2": {"style":"Default","layer":1}
}
```

The generated result uses one `kdenlive_add_subtitle_batch` operation per speaker, so interview captions remain editable and can be restyled independently in the editor.

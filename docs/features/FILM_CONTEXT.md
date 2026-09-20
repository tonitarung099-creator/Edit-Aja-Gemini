# Film Context

Film Context is an optional local capability for **Update P5 Edit Aja**. It gives an AI agent a small searchable memory of a movie so the agent does not need to inspect or upload the full movie on every request.

It is deliberately separate from **AI Edit JSON**:

- Film Context answers: *what is in the source movie and where is it?*
- AI Edit JSON answers: *what timeline edits should Edit Aja execute?*

Film Context itself never edits the timeline.

## Design goals

1. Local-first. Building/searching the base index uses no API.
2. Optional. Edit Aja must remain usable when Film Context is disabled or absent.
3. Text-first escalation. Return timestamps/dialogue first; generate images only for a few requested candidates.
4. Reusable cache. Index a movie once and reuse it in later projects.
5. Small model context. AI providers receive compact JSON results instead of a whole-film dump.
6. Stable tool protocol. Gemini, OpenAI-compatible agents, MCP adapters, or future local agents can use the same movie tools.

## Current Phase 15 core

The base implementation is dependency-light:

- FFmpeg scene-change detection
- FFprobe duration lookup
- optional SRT parsing
- SQLite scene/subtitle database
- local BM25 ranking over dialogue + local scene notes
- optional continuity bias with \`near_scene\`
- neighboring scene context
- on-demand keyframe extraction and cache
- JSON tool-call adapter

No third-party Python package is required by the core.

## Build an index

\`\`\`bash
python tools/film_context/film_context.py index movie.mp4 \
  --srt movie.srt \
  --index-dir .film-context/movie
\`\`\`

The output directory contains:

\`\`\`text
.film-context/movie/
  manifest.json
  movie.db
  keyframes/        # created only when keyframes are requested
\`\`\`

The initial index deliberately does **not** render every scene to images.

## Search locally

\`\`\`bash
python tools/film_context/film_context.py search \
  "John kembali ke rumah" \
  --index-dir .film-context/movie \
  --top-k 5
\`\`\`

The result is compact JSON with scene ids, source timestamps, scores and a short dialogue/notes excerpt.

For story continuity:

\`\`\`bash
python tools/film_context/film_context.py search \
  "mencari ayahnya" \
  --index-dir .film-context/movie \
  --near-scene 214
\`\`\`

This keeps semantic text matching dominant while adding a small proximity preference.

## Read one candidate and its neighbors

\`\`\`bash
python tools/film_context/film_context.py scene 214 \
  --index-dir .film-context/movie

python tools/film_context/film_context.py context 214 \
  --index-dir .film-context/movie \
  --radius 2
\`\`\`

This is the intended AI flow:

\`\`\`text
movie_search(query)
       ↓
small Top-K list
       ↓
movie_get_context(best candidate)
       ↓
still ambiguous?
       ↓
movie_get_keyframes([candidate ids])
\`\`\`

Only the final step generates image files.

## On-demand keyframes

\`\`\`bash
python tools/film_context/film_context.py keyframes 214 216 \
  --index-dir .film-context/movie \
  --count 2
\`\`\`

Film Context chooses times inside each scene rather than exact cut boundaries, reducing accidental transition/black frames. A maximum of a few frames per requested scene is intended.

## Stable AI tool protocol

\`\`\`bash
python tools/film_context/film_context.py tool-catalog
\`\`\`

Phase 15 exposes these names:

- \`movie_context_status\`
- \`movie_search\`
- \`movie_get_scene\`
- \`movie_get_context\`
- \`movie_get_keyframes\`

Example:

\`\`\`bash
python tools/film_context/film_context.py tool-call movie_search \
  --index-dir .film-context/movie \
  --arguments '{"query":"John pulang ke rumah","top_k":3}'
\`\`\`

Every core response records \`api_used: false\` when relevant. An adapter may later decide whether to send only those compact results to Gemini or another provider.

## Scene notes / future local intelligence

The \`notes\` column is intentionally part of the index now:

\`\`\`bash
python tools/film_context/film_context.py annotate 214 \
  "John enters the house and finds his father missing" \
  --index-dir .film-context/movie
\`\`\`

Later optional local semantic/vision engines can populate these notes or add vector indexes without changing the public tool names. No heavy vision model is bundled in Phase 15.

## Optional visual semantic tags

The base Film Context remains lightweight and does not require a vision model. For users who want better visual understanding, Phase 15 can optionally run OpenCLIP **once during indexing**:

```bash
python tools/film_context/film_context.py visual-index \
  --index-dir .film-context/movie
```

This optional command requires `open_clip_torch`, PyTorch and Pillow. They are **not bundled with the base editor**.

The visual index deliberately avoids loading a large model during every AI query:

```text
movie scenes
   ↓
one representative mid-frame per scene
   ↓
OpenCLIP once during indexing
   ↓
top bilingual semantic tags
   ↓
SQLite scene_visual cache
   ↓
normal movie_search
(no vision model loaded)
```

Examples of persisted tags include:

```text
person opening a door / orang membuka pintu
inside a house / dalam rumah
person crying / orang menangis
car crash / kecelakaan mobil
document or letter / dokumen surat
```

The vocabulary is intentionally recap-oriented and bilingual so Indonesian narration can benefit from the same local search. The OpenCLIP model is only needed when building or rebuilding these tags. After that, normal `movie_search` remains a lightweight SQLite/BM25 lookup over dialogue, notes and cached visual tags.

This is an optional semantic-tag layer, not a mandatory video-language model. A future backend can store richer free-form vectors without changing the existing `movie_*` tool protocol.


## Privacy and API budget

The intended escalation policy is:

\`\`\`text
LEVEL 0  Local search only
LEVEL 1  Compact timestamps/dialogue JSON
LEVEL 2  Neighbor scene context
LEVEL 3  A few candidate keyframes
LEVEL 4  Short clip only if a future adapter explicitly needs motion
\`\`\`

The entire source movie is never required as an API prompt.

## Native AI Assistant integration

Phase 15 also adds Film Context directly to the existing AI Assistant without creating a second editor or timeline.

- Film Context is **disabled by default**.
- The panel can choose an existing local index or build one from a movie plus optional SRT.
- A separate **Build Visual Index (Optional)…** button runs the OpenCLIP semantic-tag pass only when the user wants it; normal Film Context does not require OpenCLIP/PyTorch.
- The existing built-in AI Agent receives the five `movie_*` tools only as an extra capability.
- The agent is instructed to search compact text candidates first, then inspect neighboring scenes, then request keyframes only if needed.
- `movie_get_keyframes` may attach up to six selected candidate images when the existing vision-frame option is enabled.
- The source movie itself is not attached as a whole-film API prompt.
- ChatGPT/AI Edit JSON is unchanged and remains a separate timeline-command path.
- Once an AI decides what to edit, normal native timeline tools remain the executor.

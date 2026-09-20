# AI Asset Manifest

AI Asset Manifest connects **B-roll planning** to AI image/video generation without coupling Update P5 to any one generation provider.

## Build generation jobs

```text
python tools/asset_manifest/asset_manifest.py make broll-plan.json \
  --output asset-manifest.json
```

Each item contains:

- stable B-roll slot ID,
- visual type,
- timeline position and duration,
- aspect ratio,
- resolution,
- generation prompt,
- deterministic target filename.

A global documentary style prefix is added to every prompt so a full video can keep consistent visual direction.

## Generate externally

The manifest can be used by ChatGPT/GPT Images, another image generator, a local model, or a future MCP/API integration. Update P5 does not require any one image-generation service.

## Resolve generated files

Put the generated assets in one folder, keeping the suggested filenames when possible:

```text
python tools/asset_manifest/asset_manifest.py resolve \
  asset-manifest.json ./generated-assets \
  --asset-map broll-assets.json \
  --report asset-resolution.json
```

The resolver matches exact filenames first, then stable slot IDs. The resulting `broll-assets.json` is directly accepted by the Transcript B-roll Planner's `assets` command, completing:

```text
transcript
 → B-roll plan
 → AI Asset Manifest
 → generated images/video
 → resolved asset map
 → native timeline B-roll
```

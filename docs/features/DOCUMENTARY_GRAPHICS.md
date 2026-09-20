# Documentary Graphics Generator

Update P5 can generate lightweight **SVG graphics** and insert them into the native timeline.

Kdenlive/MLT supports SVG image assets, so the graphics remain ordinary replaceable media rather than being burned permanently into rendered video.

Implemented:

- horizontal bar charts,
- line charts,
- documentary timelines,
- map overlays with latitude/longitude pins,
- optional embedded map background image,
- automatic Phase 6 import/insert/resize plan generation.

## Compile graphics

```text
python tools/documentary_graphics/documentary_graphics.py \
  examples/documentary/japan-data-graphics.json \
  --output-dir generated-graphics \
  --plan-output graphics.edit.json
```

This produces one SVG per graphic plus a Phase 6 edit plan that places each asset at its requested timeline position.

## Map graphics

Map points may use:

```json
{"lat": 35.6762, "lon": 139.6503, "label": "Tokyo"}
```

or normalized `x/y` coordinates. Without a background image, the generator uses a clean equirectangular grid. With `background_image`, the image is embedded directly into the SVG and pins are placed above it.

This generator intentionally keeps data rendering independent from AI. ChatGPT can author the JSON; the local tool renders deterministic assets and the editor performs native insertion.

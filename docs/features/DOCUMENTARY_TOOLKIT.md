# Documentary Toolkit

The Documentary Toolkit compiles common creator/documentary editing patterns into Phase 6 AI Edit JSON. All generated elements remain editable in the native timeline.

Implemented building blocks:

- lower thirds,
- chapter cards,
- quote/source cards,
- B-roll insertion,
- B-roll placeholders for assets that will be generated or sourced later,
- segmented Ken Burns photo motion,
- multi-operation documentary configs.

## Compile a documentary graphics package

```text
python tools/documentary_toolkit/documentary_toolkit.py compile \
  examples/documentary/japan-documentary.json \
  --output japan-graphics.edit.json
```

Then import the resulting file through Update P5's AI Edit JSON workflow.

## B-roll placeholders

A placeholder is an editable title clip labeled with the asset that should eventually occupy that range. This is useful when ChatGPT has already decided **what** should appear but the actual AI image/video is still being generated.

```text
python tools/documentary_toolkit/documentary_toolkit.py placeholder \
  "Map of Japan during the Tokugawa era" \
  --at 31 \
  --duration 5 \
  --output broll-slot.json
```

## Ken Burns

```text
python tools/documentary_toolkit/documentary_toolkit.py ken-burns photo.jpg \
  --at 12 \
  --duration 6 \
  --segments 8 \
  --start-scale 105 \
  --end-scale 125 \
  --output photo-motion.json
```

The current implementation uses several short native clip segments with slightly different Transform values. This keeps the result deterministic and editable without depending on fragile effect-keyframe parameter layouts.

## Config operations

Supported `type` values:

- `lower_third`
- `chapter_card`
- `quote_card`
- `broll`
- `broll_placeholder`
- `ken_burns`

The toolkit is intentionally a compiler, not another AI agent. ChatGPT can author the config; Update P5 turns it into native timeline operations.

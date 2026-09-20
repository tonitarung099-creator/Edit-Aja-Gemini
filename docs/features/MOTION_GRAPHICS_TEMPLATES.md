# Motion Graphics Templates

Update P5 now includes reusable editorial/documentary motion-graphics templates built from staged SVG assets.

Implemented templates:

- **stat_reveal** — headline → large number/date → subtitle → source,
- **comparison** — left/right comparison reveal,
- **callout** — kicker → headline → explanation,
- **progress** — staged percentage/progress reveal.

## Compile

```text
python tools/motion_graphics_templates/motion_graphics_templates.py \
  examples/documentary/motion-graphics-templates.json \
  --output-dir generated-motion \
  --plan-output motion.edit.json
```

Each template is rendered as several SVG stages and placed sequentially on a native video track. This creates a simple reveal animation without flattening the entire project into one rendered motion-graphics video.

The templates are intentionally generic editorial/documentary patterns rather than copies of any specific publication's proprietary design system.

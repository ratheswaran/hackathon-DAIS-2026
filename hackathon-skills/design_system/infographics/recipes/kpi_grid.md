# Recipe — kpi_grid

**Data shape** (`scene.data`):
d = {
  cards: [
    {
      value:      number | string,   // raw value; numbers run through H.fmt unless value_fmt given
      value_fmt?: string,            // pre-formatted display string (e.g. "6.1%", "29 in 30", "1.89M") — overrides value
      label:      string,            // descriptive label under the number (also matched against scene.highlight)
      delta?:     number | string,   // optional signed change; "+2.1M" / "-14%" / 0.12 etc.
      delta_dir?: "up" | "down",     // optional explicit direction; if omitted it is inferred from delta's sign
      sub?:       string             // optional dim one-line context under the label
    }
  ],
  columns?: number   // optional fixed column count hint (otherwise auto-fit)
}
Notes: value_fmt is preferred for percentages, ratios, and "N in M" framings that H.fmt cannot express. delta colours: up -> P.amber, down -> P.alarm. scene.highlight (string or array of label strings) recolours that card's value to its accent; all others stay cobalt (P.signal). scene.annotations[0], if present, renders as an italic-serif finding under the grid.

**Minimal sample** (`scene.data`):
```json
{
  "cards": [
    {
      "value_fmt": "6.1%",
      "label": "of the global refugee stock reached any durable solution in 2024",
      "delta": "-1.4 pts",
      "delta_dir": "down",
      "sub": "vs 2016"
    },
    {
      "value": 1890000,
      "label": "people found a durable solution",
      "delta": 0.21,
      "delta_dir": "up",
      "sub": "returns, resettlement, naturalisation"
    },
    {
      "value_fmt": "29 in 30",
      "label": "refugees simply waited another year"
    },
    {
      "value": 1620000,
      "label": "voluntary returns dominated the exit mix",
      "delta": "+4x since 2017",
      "delta_dir": "up"
    }
  ]
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
if scene.get("data") is not None:
    return scene["data"]
# Shape a KPI grid from a small DataFrame: one card per row.
# mapping: {value_col, label_col, value_fmt_col?, delta_col?, delta_dir_col?, sub_col?, top_n?}
val = mapping.get("value_col") or next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])), df.columns[-1])
lab = mapping.get("label_col") or next((c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])), df.columns[0])
vfmt = mapping.get("value_fmt_col")
dcol = mapping.get("delta_col")
ddir = mapping.get("delta_dir_col")
sub = mapping.get("sub_col")
n = int(scene.get("top_n", mapping.get("top_n", 6)))
cards = []
for _, r in df.head(n).iterrows():
    card = {"label": str(r[lab])}
    if vfmt and vfmt in df.columns and pd.notna(r[vfmt]):
        card["value_fmt"] = str(r[vfmt])
    else:
        v = pd.to_numeric(pd.Series([r[val]]), errors="coerce").iloc[0]
        card["value"] = float(v) if pd.notna(v) else str(r[val])
    if dcol and dcol in df.columns and pd.notna(r[dcol]):
        dv = pd.to_numeric(pd.Series([r[dcol]]), errors="coerce").iloc[0]
        card["delta"] = float(dv) if pd.notna(dv) else str(r[dcol])
        card["delta_dir"] = (str(r[ddir]) if (ddir and ddir in df.columns and pd.notna(r[ddir]))
                             else ("down" if (pd.notna(dv) and dv < 0) else "up"))
    if sub and sub in df.columns and pd.notna(r[sub]):
        card["sub"] = str(r[sub])
    cards.append(card)
return {"cards": cards}
```

**Notes:** - HTML-not-SVG by design: per the archetype brief and the existing `stat` renderer (`root.classed('bare', true)` + appended divs), kpi_grid appends HTML for crisp text. It does NOT call H.svg. The `.figure.bare` CSS strips the card chrome so the grid sits flat on the page, matching `stat`.
- Existing CSS classes (`vlabel`/`clabel`/`annot`) are SVG `fill:` styles, useless on HTML, so card text is inline-styled but draws ALL colours/fonts from the same CSS custom properties (var(--serif/sans/mono)) and the P palette — zero new colours, no injected <style>, identical look to the page-level `.stat-card`.
- Motion is screenshot-safe: each card's full text is painted immediately, then H.in fades opacity only (staggered). Under reduced-motion or a backgrounded/rasterized tab the final values are already present at t=0. No width/transform reveals.
- Highlight-by-colour honoured: values are cobalt (P.signal) by default; a card whose `label` is in scene.highlight gets its accent. Delta up=amber, down=alarm (sober displacement palette).
- value_fmt is the escape hatch for percentages / ratios / "N in M" strings H.fmt can't produce — prefer it for those. Numeric `value` runs through H.fmt (K/M/B).
- Delta arrows use Unicode geometric triangles (▲/▼), not emoji.
- python_shaper handles the natural DataFrame->grid (one card per row, top_n rows) when a scene gives variable_name+mapping; agents can also pass `data.cards` inline for hand-curated KPI sets (the common case for hero reframes). Register `kpi_grid` shaping in _shape_scene_data if wiring the DataFrame path (the inline-data path already works via the existing scene.data passthrough).

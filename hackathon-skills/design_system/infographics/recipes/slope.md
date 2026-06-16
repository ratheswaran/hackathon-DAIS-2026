# Recipe — slope

**Data shape** (`scene.data`):
d = {
  left_label:  string,   // x-position label for the first column (e.g. "Raw rate")
  right_label: string,   // x-position label for the second column (e.g. "Adjusted")
  y_format:    "pct" | "num",  // optional, default "pct"; "pct" expects values in 0..1
  y0:          number,   // optional y-axis floor (default 0)
  note:        string,   // optional bottom-left italic finding annotation about the crossing
  rows: [
    {
      name:  string,     // entity name (matched against scene.highlight)
      left:  number,     // value at the left x-position
      right: number,     // value at the right x-position
      or:    number,     // optional left-column rank (for "#or -> #sr" annotation on highlighted rows)
      sr:    number,     // optional right-column rank
      note:  string      // optional per-row annotation (used if or/sr absent)
    }
  ]
}
// scene.highlight = a name string OR array of names. Only highlighted entities
// get an accent colour, value labels, name label, and the rank-reversal annot;
// every other line renders neutral grey. scene.title used as svg aria-label.

**Minimal sample** (`scene.data`):
```json
{
  "left_label": "Raw coverage",
  "right_label": "Urbanisation-adjusted",
  "y_format": "pct",
  "note": "Where lines cross, the ranking lied.",
  "rows": [
    {
      "name": "Maharashtra",
      "left": 0.71,
      "right": 0.66,
      "or": 1,
      "sr": 4
    },
    {
      "name": "Tamil Nadu",
      "left": 0.58,
      "right": 0.55
    },
    {
      "name": "Karnataka",
      "left": 0.49,
      "right": 0.52
    },
    {
      "name": "Gujarat",
      "left": 0.44,
      "right": 0.47
    },
    {
      "name": "Rajasthan",
      "left": 0.4,
      "right": 0.43
    },
    {
      "name": "Bihar",
      "left": 0.32,
      "right": 0.69,
      "or": 7,
      "sr": 1
    }
  ]
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
if scene.get("data") is not None:
    return scene["data"]
mp = scene.get("mapping", {}) or {}
name_col  = mp.get("name_col")  or mp.get("label_col")
left_col  = mp.get("left_col")
right_col = mp.get("right_col")
rank_left_col  = mp.get("rank_left_col")
rank_right_col = mp.get("rank_right_col")
cols = list(df.columns)
# fall back to first non-numeric for the name, first two numerics for left/right
if not name_col:
    name_col = next((c for c in cols if not pd.api.types.is_numeric_dtype(df[c])), cols[0])
nums = [c for c in cols if pd.api.types.is_numeric_dtype(df[c]) and c != name_col]
if not left_col:
    left_col = nums[0] if nums else cols[-1]
if not right_col:
    right_col = nums[1] if len(nums) > 1 else nums[0]
rows = []
sub = df[[name_col, left_col, right_col]].dropna()
for _, r in sub.iterrows():
    row = {"name": str(r[name_col]),
           "left": float(pd.to_numeric(pd.Series([r[left_col]]), errors="coerce").iloc[0]),
           "right": float(pd.to_numeric(pd.Series([r[right_col]]), errors="coerce").iloc[0])}
    if rank_left_col and rank_left_col in df.columns:
        row["or"] = int(r.get(rank_left_col)) if pd.notna(df.loc[r.name, rank_left_col]) else None
    if rank_right_col and rank_right_col in df.columns:
        row["sr"] = int(r.get(rank_right_col)) if pd.notna(df.loc[r.name, rank_right_col]) else None
    rows.append(row)
return {
    "left_label": mp.get("left_label", left_col),
    "right_label": mp.get("right_label", right_col),
    "y_format": mp.get("y_format", "pct"),
    "rows": rows,
}
```

**Notes:** Port of the reference Simpson's-paradox renderer into the scene-engine contract. Faithful to the reference visual: two x-positions via d3.scalePoint, one line per entity connecting left->right, endpoint circles at both ends, percent y-axis, italic-serif rank-reversal annotation ("#or -> #sr") and an entity name label on the highlighted line(s). Crossing lines are the whole point (Simpson's paradox / rank reversal).

MOTION: fully compliant. All final geometry (lines, circles, labels) is drawn immediately at correct coordinates; H.in animates OPACITY only. Partial transparency on neutral lines uses the stroke-opacity ATTR (0.7), not style opacity, so H.in's element-opacity tween never clobbers it. Correct at t=0 under headless-Chrome rasterization and reduced-motion.

HIGHLIGHT-BY-COLOUR: neutral P.grey by default; only names in scene.highlight (string or array) get P.signal via H.hue, thicker stroke, larger dots, plus value labels + name label + the rank annotation. Neutrals stay quiet (no labels) to keep the crossing legible — matches the reference, which labelled only the one crossing line.

CSS: uses only existing classes (axis, vlabel, clabel, annot) and CSS vars/P hexes. No injected <style>. value y-axis assumed 0..1 fractions when y_format="pct" (the reference's coverage rates); pass y_format:"num" + a value_label scene field if you have absolute numbers.

The python_shaper is OPTIONAL and additive — slope rows are usually best passed inline as scene.data (the reference precomputes overall/std rates + ranks that SQL alone can't produce). If you do drive it from a DataFrame, mapping keys: name_col, left_col, right_col, optional left_label/right_label, rank_left_col, rank_right_col, y_format. Note: this shaper is NOT yet wired into _shape_scene_data() in compose_infographic.py — to enable DataFrame-driven slope scenes, add a `t == "slope"` branch there calling this body (or just rely on inline scene.data, which already works via the existing `scene.get("data") is not None` short-circuit).

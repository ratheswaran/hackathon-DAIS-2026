# Recipe — forest_ci

**Data shape** (`scene.data`):
d = {
  rows: [ { name: str,            // row label, e.g. "Bihar"
            iso?: str,            // optional stable key (used for y-band + highlight match); falls back to name
            or: number,          // point estimate (odds ratio); plotted on a log x-axis
            lo: number,          // 95% CI lower bound (>0, log scale)
            hi: number,          // 95% CI upper bound
            n?: number,          // sample size → dot radius (scaleSqrt); optional, defaults 0
            ref?: bool } ],       // true for the reference category (OR=1 baseline; rendered ink, bold)
  ref?: str,                      // reference category display name for the "<ref> = 1" line + axis (default derived from ref row / "reference")
  highlight_note?: str            // optional override for the finding annotation on the highlighted row; else auto "← N× lower/higher than <ref>"
}
// Sort rows OR-descending (highest-odds groups on top) before passing — the renderer preserves row order.
// scene.highlight = the name/iso of the most-extreme row to accent (signal colour) + annotate.
// scene.value_label = x-axis title (default "odds ratio vs reference — log scale").
// All odds/CI bounds must be > 0 (log scale). Compute OR + CIs upstream (logistic regression); pass inline as scene.data.

**Minimal sample** (`scene.data`):
```json
{
  "rows": [
    {
      "name": "Kerala",
      "iso": "KL",
      "or": 1.42,
      "lo": 1.31,
      "hi": 1.54,
      "n": 4100,
      "ref": false
    },
    {
      "name": "Maharashtra",
      "iso": "MH",
      "or": 1,
      "lo": 1,
      "hi": 1,
      "n": 9800,
      "ref": true
    },
    {
      "name": "Tamil Nadu",
      "iso": "TN",
      "or": 0.61,
      "lo": 0.56,
      "hi": 0.67,
      "n": 7200,
      "ref": false
    },
    {
      "name": "Rajasthan",
      "iso": "RJ",
      "or": 0.34,
      "lo": 0.31,
      "hi": 0.38,
      "n": 4600,
      "ref": false
    },
    {
      "name": "Uttar Pradesh",
      "iso": "UP",
      "or": 0.22,
      "lo": 0.19,
      "hi": 0.25,
      "n": 14800,
      "ref": false
    },
    {
      "name": "Bihar",
      "iso": "BR",
      "or": 0.059,
      "lo": 0.052,
      "hi": 0.068,
      "n": 3200,
      "ref": false
    }
  ],
  "ref": "Maharashtra",
  "highlight_note": "← 17× lower odds of facility access than Maharashtra"
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
r = scene.get("data") or {}
# forest_ci is fundamentally a precomputed-stats archetype (logistic regression
# odds ratios + 95% CIs). The DataFrame path only applies when df already holds
# one row per group/category with explicit or/lo/hi columns (e.g. a saved model
# coefficient table). Otherwise pass scene["data"] inline from the notebook.
if r.get("rows"):
    return r
or_col = mapping.get("or_col") or "or"
lo_col = mapping.get("lo_col") or "lo"
hi_col = mapping.get("hi_col") or "hi"
name_col = mapping.get("name_col") or mapping.get("label_col") or df.columns[0]
iso_col = mapping.get("iso_col")
n_col = mapping.get("n_col") or mapping.get("count_col")
ref_name = mapping.get("ref") or scene.get("ref")
sub = df.copy()
for c in (or_col, lo_col, hi_col):
    sub[c] = pd.to_numeric(sub[c], errors="coerce")
sub = sub.dropna(subset=[or_col, lo_col, hi_col])
sub = sub[(sub[or_col] > 0) & (sub[lo_col] > 0) & (sub[hi_col] > 0)]
sub = sub.sort_values(or_col, ascending=False)
rows = []
for _, x in sub.iterrows():
    nm = str(x[name_col])
    rows.append({
        "name": nm,
        "iso": str(x[iso_col]) if iso_col and iso_col in sub.columns else nm,
        "or": float(x[or_col]),
        "lo": float(x[lo_col]),
        "hi": float(x[hi_col]),
        "n": (float(x[n_col]) if n_col and n_col in sub.columns and pd.notna(x[n_col]) else 0.0),
        "ref": (ref_name is not None and nm == ref_name),
    })
out = {"rows": rows}
if ref_name is not None:
    out["ref"] = str(ref_name)
return out
```

**Notes:** - Faithful port of the reference forest builder: log x-axis, point dot + 95% CI whisker per row, dashed OR=1 reference line with "<ref> = 1" annot, dot radius ∝ sample size (scaleSqrt), OR value label (mono) at whisker's high end, stacked legend + axis title to avoid overlap.
- Contract adaptation: the reference's tri-colour group/reference scheme was folded into the engine's highlight-by-colour rule. Default rows render P.grey; the reference row (ref:true) renders P.ink + bold (it's the fixed OR=1 baseline, not a measured estimate); only scene.highlight gets the accent (P.signal). This keeps the "neutral by default, accent only the named entity" rule while preserving the visually-distinct reference baseline.
- MOTION: all geometry (whiskers, dots, labels) drawn at FINAL position immediately; only opacity is animated, per-row, via H.in on the row <g>. A t=0 screenshot / backgrounded tab shows the complete plot. CI whisker transparency uses stroke-opacity ATTR (.55) — not style opacity — so it never collides with H.in's element-opacity animation.
- The finding annotation auto-derives "← N× lower/higher than <ref>" from the highlighted row's OR (round(1/or) when or<1), or you can override via d.highlight_note (the sample hard-codes the "17×" headline). Annotation flips side: drawn left of the whisker for or≥1 rows, right of the dot for or<1 rows.
- scene.value_label overrides the x-axis title; default "odds ratio vs reference — log scale".
- viewBox 820×(dynamic height): rowH clamps 26–44px so 4–20 rows all sit cleanly; left margin auto-sizes to the longest label (capped 190px).
- forest_ci is a precomputed-stats archetype — give it scene.data inline from the logistic-regression notebook. python_shaper only fires if df already carries or/lo/hi columns (a saved coefficient table); otherwise it returns the inline data untouched.
- Uses only existing CSS classes (axis, axis-title, clabel, vlabel, annot). No <style> injected, no extra CDN.

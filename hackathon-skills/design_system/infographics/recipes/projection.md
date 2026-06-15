# Recipe — projection

**Data shape** (`scene.data`):
d = {
  series: [                       // 1..n named lines. Render order = SERIES colour order.
    { name: "History",            // end-of-line label
      role: "history",            // "history" → solid + dark ink spine + crisis-anchor; "projection" → dashed
      dashed: false,              // optional explicit override of dashed-ness (default: role==='projection')
      points: [{x: <number>, y: <number>}, ...] },
    { name: "Linear fit", role: "projection",
      points: [{x, y}, ...] },
    { name: "Exponential", role: "projection",
      points: [{x, y}, ...] }
  ],
  band: [ {x: <number>, lo: <number>, hi: <number>}, ... ],  // optional shaded uncertainty fan over projection horizon
  split_year: <number>,           // optional vertical rule: solid history ends / dashed projection begins
  threshold: <number>,            // optional horizontal reference line (e.g. 150M)
  threshold_label: "150M threshold",  // optional; defaults to "<fmt(threshold)> threshold"
  markers: [ {x: <number>, label: "exp 2027"} ],  // optional dots placed on the threshold line (crossing years)
  crisis: [ {x: <number>, label: "Syria", y?: <number>} ],  // optional event annotations dropped on the history line (y auto-snaps to nearest history point if omitted)
  fit_lo: <number>, fit_hi: <number>,  // optional → faint amber shade + "fitted on YYYY–YYYY" caption
  fit_label: "trend fitted on 2010–2024",  // optional override
  y0: <number>,                   // optional y-axis floor (default 0)
  y_format: "num" | "pct",        // default "num" (H.fmt K/M/B); "pct" → 0-dp percent
  y_suffix: "M"                   // optional unit appended to numeric y ticks/threshold label (e.g. "M")
}
// scene-level: highlight (string|array of series/marker names → accent that one), value_label (y-axis title).
// Units convention: pass y already in the display unit (e.g. millions) and set y_suffix:"M", OR pass raw persons with y_format default and let H.fmt do K/M/B.

**Minimal sample** (`scene.data`):
```json
{
  "title": "Global forced displacement, projected to 2034",
  "kicker": "UNHCR · The next decade",
  "lede": "After 2010 the count of the world's forcibly displaced went near-vertical. Two naive 'if the trend just continues' projections — a straight-line fit and a compounding one — and the wide gap between them.",
  "scenes": [
    {
      "type": "projection",
      "eyebrow": "1951–2034 · millions · end-year",
      "title": "The line doesn't stop at 2024",
      "lede": "Read these as arrows, not forecasts: the band between the two paths is the uncertainty.",
      "caption": "Solid: observed history. Dashed: naive extrapolations on the 2010–2024 trend. Source: UNHCR Refugee Data Finder.",
      "value_label": "displaced (millions)",
      "highlight": "Exponential",
      "data": {
        "y_suffix": "M",
        "split_year": 2024,
        "threshold": 150,
        "threshold_label": "150M threshold",
        "fit_lo": 2010,
        "fit_hi": 2024,
        "fit_label": "trend fitted on 2010–2024",
        "series": [
          {
            "name": "History",
            "role": "history",
            "points": [
              {
                "x": 2000,
                "y": 21.8
              },
              {
                "x": 2005,
                "y": 21
              },
              {
                "x": 2010,
                "y": 41.1
              },
              {
                "x": 2013,
                "y": 51.2
              },
              {
                "x": 2015,
                "y": 65.3
              },
              {
                "x": 2018,
                "y": 74.8
              },
              {
                "x": 2020,
                "y": 89.4
              },
              {
                "x": 2022,
                "y": 108.4
              },
              {
                "x": 2024,
                "y": 111
              }
            ]
          },
          {
            "name": "Linear fit",
            "role": "projection",
            "points": [
              {
                "x": 2010,
                "y": 47.2
              },
              {
                "x": 2015,
                "y": 67.5
              },
              {
                "x": 2020,
                "y": 87.7
              },
              {
                "x": 2024,
                "y": 103.9
              },
              {
                "x": 2030,
                "y": 143
              },
              {
                "x": 2034,
                "y": 159.2
              }
            ]
          },
          {
            "name": "Exponential",
            "role": "projection",
            "points": [
              {
                "x": 2024,
                "y": 111
              },
              {
                "x": 2027,
                "y": 150
              },
              {
                "x": 2030,
                "y": 203
              },
              {
                "x": 2034,
                "y": 302
              }
            ]
          }
        ],
        "band": [
          {
            "x": 2024,
            "lo": 103.9,
            "hi": 111
          },
          {
            "x": 2027,
            "lo": 115.6,
            "hi": 150
          },
          {
            "x": 2030,
            "lo": 143,
            "hi": 203
          },
          {
            "x": 2034,
            "lo": 159.2,
            "hi": 302
          }
        ],
        "markers": [
          {
            "x": 2027,
            "label": "exp 2027"
          },
          {
            "x": 2031,
            "label": "linear 2031"
          }
        ],
        "crisis": [
          {
            "x": 2011,
            "label": "Syria"
          },
          {
            "x": 2022,
            "label": "Ukraine"
          }
        ]
      }
    }
  ],
  "methodology": "Linear = OLS on 2010–2024; exponential = 2024 total compounded at the 2010→2024 CAGR. The two paths are the uncertainty band; neither is a UNHCR forecast.",
  "source": "Source: UNHCR Refugee Data Finder, CC BY 4.0."
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
mp = mapping or {}
x_col = mp.get("x_col") or df.columns[0]
y_col = mp.get("y_col") or next((c for c in df.columns if c != x_col and pd.api.types.is_numeric_dtype(df[c])), df.columns[-1])
series_col = mp.get("series_col")           # column naming each line (e.g. 'series': History/Linear/Exponential)
role_col = mp.get("role_col")               # optional column with 'history'/'projection' per row
split_year = mp.get("split_year") or scene.get("split_year")
threshold = mp.get("threshold") or scene.get("threshold")

sub = df.copy()
sub[x_col] = pd.to_numeric(sub[x_col], errors="coerce")
sub[y_col] = pd.to_numeric(sub[y_col], errors="coerce")
sub = sub.dropna(subset=[x_col, y_col])

series = []
if series_col and series_col in sub.columns:
    for name, grp in sub.groupby(series_col):
        grp = grp.sort_values(x_col)
        pts = [{"x": float(r[x_col]), "y": float(r[y_col])} for _, r in grp.iterrows()]
        # role: explicit column, else infer 'history' if the line straddles split, else 'projection'
        if role_col and role_col in grp.columns:
            role = str(grp[role_col].iloc[0]).lower()
        elif split_year is not None and grp[x_col].min() < float(split_year):
            role = "history"
        else:
            role = "projection"
        series.append({"name": str(name), "role": role, "points": pts})
else:
    pts = [{"x": float(r[x_col]), "y": float(r[y_col])} for _, r in sub.sort_values(x_col).iterrows()]
    series.append({"name": mp.get("y_label", str(y_col)), "role": "history", "points": pts})

# optional uncertainty band from lo/hi columns
band = []
lo_col, hi_col = mp.get("lo_col"), mp.get("hi_col")
if lo_col and hi_col and lo_col in df.columns and hi_col in df.columns:
    bsub = df[[x_col, lo_col, hi_col]].copy()
    bsub[x_col] = pd.to_numeric(bsub[x_col], errors="coerce")
    bsub[lo_col] = pd.to_numeric(bsub[lo_col], errors="coerce")
    bsub[hi_col] = pd.to_numeric(bsub[hi_col], errors="coerce")
    bsub = bsub.dropna().sort_values(x_col)
    band = [{"x": float(r[x_col]), "lo": float(r[lo_col]), "hi": float(r[hi_col])} for _, r in bsub.iterrows()]

out = {"series": series, "band": band}
if split_year is not None:
    out["split_year"] = float(split_year)
if threshold is not None:
    out["threshold"] = float(threshold)
for k in ("y_format", "y_suffix", "fit_lo", "fit_hi", "y0", "threshold_label", "fit_label"):
    if mp.get(k) is not None:
        out[k] = mp[k]
return out
```

**Notes:** - Faithful port of build_nextdecade.py, adapted to the scene-engine contract. The reference's spec hint (`series:[{x,y}], band:[{x,lo,hi}], split_year`) is generalized: `series` is a LIST of named lines (`{name, role, points:[{x,y}]}`) so the dual linear/exponential idea ports cleanly — one history line + n projection lines. A single-line projection still works (one series, role 'history').

- MOTION is fully compliant: every line is drawn with its FINAL `d` immediately (and dashed projections get their resting `stroke-dasharray:'6,5'` attr up front), the band gets its resting `fill-opacity:.22` attr; H.in then fades OPACITY only. No stroke-dashoffset draw-on, no clip-rect width growth, no width/r reveals (the original used both — deliberately replaced). A t=0 screenshot or backgrounded tab shows correct geometry. RM-safe via H.in.

- Colour: history renders dark ink (the spine) by default; projection lines take SERIES[] colours; markers/crossing-dots take SERIES[]. Set scene.highlight to a series name (or array) to accent just that path/marker via H.hue (grey otherwise). The sample highlights "Exponential".

- Dashed-ness is driven by `role==='projection'` OR explicit `dashed:true`. A projection line that overlaps the history range (the OLS in-sample fit) is fine — it just draws across its full x-extent, exactly like the reference's faint guide line, but here as a normal dashed series.

- Crisis annotations auto-snap their y to the nearest point on the reference (history/first) series if `y` is omitted, mirroring the reference dropping Syria/Ukraine markers onto the history curve.

- Units: pass y in display units + `y_suffix:"M"` (axis ticks/threshold label append it; sample does this), OR pass raw persons and leave defaults so H.fmt renders K/M/B. `y_format:'pct'` switches the axis to 0-dp percent.

- python_shaper covers the natural DataFrame→shape: long table with x_col + y_col (+ optional series_col / role_col / lo_col / hi_col). For OLS/CAGR-derived projection points and crossing years (which SQL can't compute), the agent should pass the scene `data` inline — the tool uses inline data verbatim per _shape_scene_data. The shaper is for the case where projection rows are already materialized in a DataFrame.

- Uses ONLY existing CSS classes (axis, axis-title, vlabel via none here, clabel, annot) and P palette + SERIES. No injected <style>, no extra CDN. viewBox 720x440 matches the wide line_multi sibling.

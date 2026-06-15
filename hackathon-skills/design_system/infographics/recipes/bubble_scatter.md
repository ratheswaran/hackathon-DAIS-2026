# Recipe — bubble_scatter

**Data shape** (`scene.data`):
d = {
  points: [                       // one per hosting country
    { name: "Lebanon",            // short display label (already shortened)
      region: "Asia",             // region bucket → colour (must be in `regions`)
      gdp: 4136,                  // GDP per capita, US$ (>0; log x)
      per1000: 134.5,             // refugees hosted per 1,000 residents (>0; log y)
      hosted: 815000,            // total refugees hosted → bubble area
      note: true },               // truthy → label this point (notable outlier)
    ...
  ],
  regions: ["Africa","Asia","Europe","Americas"],  // optional; legend + colour domain. If omitted, derived from points (in first-seen order).
  intercept: -2.1,  // OLS log-log fit: log10(per1000) = intercept + slope*log10(gdp). Both optional; omit → no fit line.
  slope: 0.18,
  r: 0.22,          // Pearson r on log scales (optional → r annotation)
  r2: 0.05,         // R² (optional)
  p: 0.041,         // p-value for slope (optional)
  x_label: "GDP per capita, US$ (log scale)",        // optional axis title override
  y_label: "refugees hosted per 1,000 residents (log)" // optional
}
Notes: colour ENCODES region (SERIES ordinal over `regions`), NOT highlight-by-colour. scene.highlight (string or array of point names) optionally adds a label to those points (in addition to any with note:true). Points with non-positive gdp/per1000/hosted are dropped (log scale).

**Minimal sample** (`scene.data`):
```json
{
  "points": [
    {
      "name": "Lebanon",
      "region": "Asia",
      "gdp": 4136,
      "per1000": 134.5,
      "hosted": 815000,
      "note": true
    },
    {
      "name": "Jordan",
      "region": "Asia",
      "gdp": 4204,
      "per1000": 64.2,
      "hosted": 700000,
      "note": true
    },
    {
      "name": "Chad",
      "region": "Africa",
      "gdp": 716,
      "per1000": 71.8,
      "hosted": 1200000,
      "note": true
    },
    {
      "name": "Uganda",
      "region": "Africa",
      "gdp": 964,
      "per1000": 33.4,
      "hosted": 1600000,
      "note": true
    },
    {
      "name": "Türkiye",
      "region": "Asia",
      "gdp": 13383,
      "per1000": 38.9,
      "hosted": 3300000,
      "note": true
    },
    {
      "name": "Germany",
      "region": "Europe",
      "gdp": 52746,
      "per1000": 30.5,
      "hosted": 2550000,
      "note": true
    },
    {
      "name": "Iran",
      "region": "Asia",
      "gdp": 4388,
      "per1000": 41.2,
      "hosted": 3760000,
      "note": false
    },
    {
      "name": "Pakistan",
      "region": "Asia",
      "gdp": 1568,
      "per1000": 8.4,
      "hosted": 2020000,
      "note": false
    },
    {
      "name": "France",
      "region": "Europe",
      "gdp": 44408,
      "per1000": 9.1,
      "hosted": 620000,
      "note": false
    },
    {
      "name": "USA",
      "region": "Americas",
      "gdp": 81695,
      "per1000": 1.2,
      "hosted": 421000,
      "note": true
    },
    {
      "name": "Colombia",
      "region": "Americas",
      "gdp": 6624,
      "per1000": 56.7,
      "hosted": 2890000,
      "note": false
    },
    {
      "name": "Ethiopia",
      "region": "Africa",
      "gdp": 1027,
      "per1000": 8.3,
      "hosted": 1020000,
      "note": false
    },
    {
      "name": "Kenya",
      "region": "Africa",
      "gdp": 2110,
      "per1000": 14.6,
      "hosted": 770000,
      "note": false
    },
    {
      "name": "Poland",
      "region": "Europe",
      "gdp": 22057,
      "per1000": 25.4,
      "hosted": 950000,
      "note": false
    }
  ],
  "regions": [
    "Africa",
    "Asia",
    "Europe",
    "Americas"
  ],
  "intercept": 1.45,
  "slope": 0.06,
  "r": 0.22,
  "r2": 0.05,
  "p": 0.041,
  "x_label": "GDP per capita, US$ (log scale)",
  "y_label": "refugees hosted per 1,000 residents (log)"
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
r = scene.get("data") or {}
# This archetype expects PRECOMPUTED stats (OLS fit, r/R2/p) the agent supplies
# inline via scene["data"] — SQL/pandas alone can't do the log-log regression.
# If a DataFrame + mapping is given, shape the `points` array and pass through
# any precomputed regions/intercept/slope/r/r2/p the agent already put in `data`.
if df is None or df.empty:
    return r
m = mapping or {}
name_col = m.get("name_col") or m.get("label_col")
region_col = m.get("region_col")
gdp_col = m.get("gdp_col") or m.get("x_col")
per1000_col = m.get("per1000_col") or m.get("y_col")
hosted_col = m.get("hosted_col") or m.get("size_col")
note_col = m.get("note_col")
sub = df.copy()
for c in (gdp_col, per1000_col, hosted_col):
    if c in sub.columns:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")
sub = sub.dropna(subset=[c for c in (gdp_col, per1000_col, hosted_col) if c in sub.columns])
sub = sub[(sub[gdp_col] > 0) & (sub[per1000_col] > 0) & (sub[hosted_col] > 0)]
points = []
for _, row in sub.iterrows():
    pt = {
        "name": str(row[name_col]) if name_col in sub.columns else "",
        "region": str(row[region_col]) if region_col and region_col in sub.columns else "Other",
        "gdp": float(row[gdp_col]),
        "per1000": float(row[per1000_col]),
        "hosted": float(row[hosted_col]),
    }
    if note_col and note_col in sub.columns:
        pt["note"] = bool(row[note_col])
    points.append(pt)
regions = r.get("regions")
if not regions and region_col and region_col in sub.columns:
    seen, regions = set(), []
    for rg in sub[region_col].astype(str):
        if rg not in seen:
            seen.add(rg); regions.append(rg)
out = {"points": points}
if regions:
    out["regions"] = regions
for k in ("intercept", "slope", "r", "r2", "p", "x_label", "y_label"):
    if r.get(k) is not None:
        out[k] = r[k]
return out
```

**Notes:** Faithful port of build_bubble.py. Key fidelity points and deltas vs the reference:

1. COLOUR ENCODES REGION (d3.scaleOrdinal over SERIES), NOT the engine's usual highlight-by-colour. This matches the reference exactly (region ramp). scene.highlight is repurposed: it only adds a label to the named point(s), on top of any point with note:true. If you want zero region colouring you'd need a different archetype.

2. CSS-class remap (reference used classes that do NOT exist in _SCAFFOLD): albl→clabel (sans, ink, 600 — visually identical), legend→clabel at 11px, the r/R² finding→annot (italic serif), axis titles→axis-title (the engine's class is mono/uppercase, so they render uppercased — a minor styling change from the reference's sentence-case .axt; acceptable and on-brand).

3. MOTION: every element draws at FINAL geometry (cx/cy/r/line endpoints set immediately); only opacity fades via H.in. Partial bubble transparency uses the fill-opacity ATTR (not style opacity, which H.in owns). A screenshot at t=0 shows correct geometry. Bubble fade delay is capped (Math.min(i*18,700)) so many points don't stagger past ~0.7s.

4. r/R² annotation is anchored top-left of the plot (x=8,y=14) so it never collides with the regression line or the right-gutter legends. Wording "significant, but practically negligible" is the reference's editorial finding (R²≈0.05); if the agent's data shows a strong fit this sentence would be wrong — consider gating it or letting the agent override via scene.caption. Left as-is to match the validated story.

5. Inline-data archetype: r/r2/p/slope/intercept are PRECOMPUTED by the agent (log-log OLS — SQL can't do it), passed via scene["data"]. The python_shaper only assists when a DataFrame is also supplied (shapes the points array, preserves the agent's stat keys). Most callers will just pass scene["data"] inline, in which case _shape_scene_data returns it verbatim and the shaper isn't invoked.

6. Stroke colour on bubbles is P.paper (the canvas) for the halo separation — reference used --ivory (its paper). No extra CDN needed; pure d3 v7.

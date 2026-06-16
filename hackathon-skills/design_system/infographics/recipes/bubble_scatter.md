# Recipe — bubble_scatter

**Data shape** (`scene.data`):
d = {
  points: [                       // one per district
    { name: "Araria",             // short display label (already shortened)
      region: "East",             // region bucket → colour (must be in `regions`)
      gdp: 78.4,                  // health-burden index, HBI (>0; log x) — the "need" axis
      per1000: 0.3,               // facility coverage per district (>0; log y) — the "supply" axis
      hosted: 320,               // sampled facilities in the district → bubble area
      note: true },               // truthy → label this point (notable outlier)
    ...
  ],
  regions: ["North","South","East","West"],  // optional; legend + colour domain. If omitted, derived from points (in first-seen order).
  intercept: -2.1,  // OLS log-log fit: log10(per1000) = intercept + slope*log10(gdp). Both optional; omit → no fit line.
  slope: 0.18,
  r: 0.22,          // Pearson r on log scales (optional → r annotation)
  r2: 0.05,         // R² (optional)
  p: 0.041,         // p-value for slope (optional)
  x_label: "health-burden index (log scale)",        // optional axis title override
  y_label: "facility coverage (log)"                  // optional
}
Notes: colour ENCODES region (SERIES ordinal over `regions`), NOT highlight-by-colour. scene.highlight (string or array of point names) optionally adds a label to those points (in addition to any with note:true). Points with non-positive gdp/per1000/hosted are dropped (log scale). NB: facilities is a ~10k SAMPLE, so the y-axis is COVERAGE not true supply, and there is no per-capita (no population in the dataset).

**Minimal sample** (`scene.data`):
```json
{
  "points": [
    {
      "name": "Araria",
      "region": "East",
      "gdp": 78.4,
      "per1000": 0.6,
      "hosted": 4,
      "note": true
    },
    {
      "name": "Kishanganj",
      "region": "East",
      "gdp": 74.1,
      "per1000": 0.4,
      "hosted": 3,
      "note": true
    },
    {
      "name": "Shrawasti",
      "region": "North",
      "gdp": 71.8,
      "per1000": 0.5,
      "hosted": 3,
      "note": true
    },
    {
      "name": "Barwani",
      "region": "West",
      "gdp": 66.4,
      "per1000": 1.1,
      "hosted": 7,
      "note": true
    },
    {
      "name": "Nandurbar",
      "region": "West",
      "gdp": 63.9,
      "per1000": 2.0,
      "hosted": 12,
      "note": true
    },
    {
      "name": "Lucknow",
      "region": "North",
      "gdp": 39.5,
      "per1000": 18.3,
      "hosted": 210,
      "note": true
    },
    {
      "name": "Patna",
      "region": "East",
      "gdp": 44.2,
      "per1000": 14.1,
      "hosted": 168,
      "note": false
    },
    {
      "name": "Indore",
      "region": "West",
      "gdp": 36.8,
      "per1000": 12.6,
      "hosted": 140,
      "note": false
    },
    {
      "name": "Chennai",
      "region": "South",
      "gdp": 28.4,
      "per1000": 22.7,
      "hosted": 260,
      "note": false
    },
    {
      "name": "Mumbai",
      "region": "West",
      "gdp": 24.1,
      "per1000": 31.2,
      "hosted": 380,
      "note": true
    },
    {
      "name": "Coimbatore",
      "region": "South",
      "gdp": 26.7,
      "per1000": 9.8,
      "hosted": 96,
      "note": false
    },
    {
      "name": "Thiruvananthapuram",
      "region": "South",
      "gdp": 16.9,
      "per1000": 19.4,
      "hosted": 220,
      "note": false
    },
    {
      "name": "Ernakulam",
      "region": "South",
      "gdp": 18.2,
      "per1000": 24.0,
      "hosted": 290,
      "note": false
    },
    {
      "name": "Pune",
      "region": "West",
      "gdp": 25.5,
      "per1000": 16.7,
      "hosted": 198,
      "note": false
    }
  ],
  "regions": [
    "North",
    "South",
    "East",
    "West"
  ],
  "intercept": 1.45,
  "slope": -0.06,
  "r": -0.19,
  "r2": 0.04,
  "p": 0.041,
  "x_label": "health-burden index (log scale)",
  "y_label": "facility coverage (log)"
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

**Notes:** Faithful port of the reference bubble builder. Key fidelity points and deltas vs the reference:

1. COLOUR ENCODES REGION (d3.scaleOrdinal over SERIES), NOT the engine's usual highlight-by-colour. This matches the reference exactly (region ramp). scene.highlight is repurposed: it only adds a label to the named point(s), on top of any point with note:true. If you want zero region colouring you'd need a different archetype.

2. CSS-class remap (reference used classes that do NOT exist in _SCAFFOLD): albl→clabel (sans, ink, 600 — visually identical), legend→clabel at 11px, the r/R² finding→annot (italic serif), axis titles→axis-title (the engine's class is mono/uppercase, so they render uppercased — a minor styling change from the reference's sentence-case .axt; acceptable and on-brand).

3. MOTION: every element draws at FINAL geometry (cx/cy/r/line endpoints set immediately); only opacity fades via H.in. Partial bubble transparency uses the fill-opacity ATTR (not style opacity, which H.in owns). A screenshot at t=0 shows correct geometry. Bubble fade delay is capped (Math.min(i*18,700)) so many points don't stagger past ~0.7s.

4. r/R² annotation is anchored top-left of the plot (x=8,y=14) so it never collides with the regression line or the right-gutter legends. Wording "significant, but practically negligible" is the reference's editorial finding (R²≈0.05); if the agent's data shows a strong fit this sentence would be wrong — consider gating it or letting the agent override via scene.caption. Left as-is to match the validated story.

5. Inline-data archetype: r/r2/p/slope/intercept are PRECOMPUTED by the agent (log-log OLS — SQL can't do it), passed via scene["data"]. The python_shaper only assists when a DataFrame is also supplied (shapes the points array, preserves the agent's stat keys). Most callers will just pass scene["data"] inline, in which case _shape_scene_data returns it verbatim and the shaper isn't invoked.

6. Stroke colour on bubbles is P.paper (the canvas) for the halo separation — reference used --ivory (its paper). No extra CDN needed; pure d3 v7.

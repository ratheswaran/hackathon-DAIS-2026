# Recipe — pyramid

**Data shape** (`scene.data`):
d = {
  bands: [ {age: string, female: number, male: number}, ... ],  // rows top→bottom; values in a common unit
  unit?: string   // e.g. 'M' (millions) appended to axis ticks; '' for raw counts
}
Ordering: pass bands in display order (e.g. '0-4' at top → '60+' at bottom, OR oldest-first — the renderer preserves array order top-to-bottom).
scene.highlight (optional): 'female' dims the male side (foreground women & girls — the reference's highlightFemale mode); 'male' dims the female side; null/absent = both sides full strength.
scene.annotation (optional): string OR {text, side?: 'left'|'right', band_index?: int} — an italic-serif finding annotation. Also accepts scene.annotations[0].
The two-toned female=signal/male=slate encoding is intrinsic (it is the chart's meaning) and is NOT overridden by scene.highlight to a single colour — highlight only dims one side.

**Minimal sample** (`scene.data`):
```json
{
  "type": "pyramid",
  "title": "Population pyramid — forcibly displaced, 2024",
  "eyebrow": "UNHCR · Demographics",
  "lede": "Almost half are children. Among displaced people whose age is recorded, 45% are under 18 — against roughly 30% worldwide.",
  "highlight": "female",
  "caption": "Female (left) and male (right) by age band. Source: UNHCR Refugee Data Finder.",
  "annotation": {
    "text": "← almost half under 18",
    "side": "left",
    "band_index": 4
  },
  "data": {
    "unit": "M",
    "bands": [
      {
        "age": "0-4",
        "female": 7.8,
        "male": 8.1
      },
      {
        "age": "5-11",
        "female": 9.6,
        "male": 10.2
      },
      {
        "age": "12-17",
        "female": 6.4,
        "male": 6.9
      },
      {
        "age": "18-59",
        "female": 18.3,
        "male": 16.1
      },
      {
        "age": "60+",
        "female": 3.1,
        "male": 2.4
      }
    ]
  }
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
if scene.get("data") is not None:
    return scene["data"]
mp = scene.get("mapping", {}) or {}
age_col = mp.get("age_col") or df.columns[0]
fem_col = mp.get("female_col")
mal_col = mp.get("male_col")
# fall back to the first two numeric columns if not named
if not fem_col or not mal_col:
    nums = [c for c in df.columns if c != age_col and pd.api.types.is_numeric_dtype(df[c])]
    fem_col = fem_col or (nums[0] if len(nums) > 0 else df.columns[-2])
    mal_col = mal_col or (nums[1] if len(nums) > 1 else df.columns[-1])
unit = mp.get("unit", "")
scale = float(mp.get("scale", 1.0))  # e.g. 1e-6 to express raw persons in millions (pair with unit='M')
sub = df[[age_col, fem_col, mal_col]].copy()
sub[fem_col] = pd.to_numeric(sub[fem_col], errors="coerce")
sub[mal_col] = pd.to_numeric(sub[mal_col], errors="coerce")
sub = sub.dropna()
bands = [
    {"age": str(r[age_col]),
     "female": round(float(r[fem_col]) * scale, 4),
     "male": round(float(r[mal_col]) * scale, 4)}
    for _, r in sub.iterrows()
]
return {"bands": bands, "unit": unit}
```

**Notes:** Faithful port of build_flagship.py renderPyramid: female-left / male-right diverging bars, symmetric linear x-scale domain [-maxV, maxV] with maxV = 1.12 * max(any cell), centred age-band labels, "Female"/"Male" side headers above the axes, abs-value axis ticks with a unit suffix.

DEVIATIONS / decisions:
- Reference colours were clay(female)/blue(male) from its own palette. Mapped into the engine palette: female=P.signal (cobalt primary), male=P.slate. This two-tone split IS the chart's encoding, so it is intentionally NOT collapsed to a single highlight colour. scene.highlight === 'female' reproduces the reference's `highlightFemale` mode (dims the male side via fill-opacity 0.30); 'male' dims the other side. With no highlight, both sides render at fill-opacity 0.92 (matching the reference resting state).
- MOTION: final geometry is set immediately on every rect; H.in animates ONLY element opacity (style). The dim effect uses the fill-opacity ATTR so it survives — H.in owns element 'opacity', so the two compose (element-opacity fade × fill-opacity dim) without clobbering. A backgrounded tab / headless-Chrome screenshot at t=0 shows full correct geometry.
- viewBox 720x460 (wide chart; slightly taller than the 420 default to give 5-7 age bands room — adjust by editing Hh if many bands).
- unit: pass 'M' when your female/male values are already in millions (the reference pre-divides persons by 1e6). The python_shaper supports a `scale` mapping (e.g. 1e-6) to convert raw person counts to millions; pair it with unit='M'.
- Axis tick formatter: integers/commas for >=1e3 via H.fmt, else 1-dp for fractional millions, then the unit suffix — so '7.8M', '10M', '0' all read cleanly.
- Annotation is optional and accepts a string, or {text, side, band_index} to place an italic-serif finding near a specific band (default: left of the top band). Also reads scene.annotations[0] for engine-wide consistency.
- Uses ONLY existing CSS classes (axis, clabel, annot) and palette/H helpers; no injected <style>, no extra CDN.
- python_shaper expects a wide DataFrame (one row per age band, separate female & male numeric columns). mapping keys: age_col, female_col, male_col, unit, scale. Inline scene.data takes precedence (returned verbatim) so the agent can hand-build the pyramid when the demographic split is computed outside SQL.

# Recipe — choropleth

**Data shape** (`scene.data`):
d = {
  vals: { <numericISO(int)>: { name: string, rate: number(0..1), n?: number } },  // REQUIRED. Keyed by the country's ISO-3166-1 *numeric* code because the world-atlas TopoJSON features are keyed by feature.id = numeric code. e.g. {276:{name:"Germany",rate:0.96,n:142000}}.
  label_iso?: number[],   // optional list of numeric ISO codes to direct-label on the map. If omitted/empty, ALL valued countries are labelled.
  frame?: [[lon,lat],...], // optional 4 corner points for the Europe MultiPoint frame; default [[-12,34],[46,34],[46,72],[-12,72]].
  finding?: string,        // optional inline serif finding annotation; only used if scene.annotations[0] is absent.
  atlas_url?: string       // optional override for the world-atlas TopoJSON URL.
}
// Scene meta consumed: scene.title (aria), scene.value_label (legend heading, default "recognition rate"),
// scene.highlight (string name OR array of names -> accented label + ink-stroke outline),
// scene.annotations[0] (preferred serif finding text).

**Minimal sample** (`scene.data`):
```json
{
  "vals": {
    "250": {
      "name": "France",
      "rate": 0.62,
      "n": 51000
    },
    "276": {
      "name": "Germany",
      "rate": 0.96,
      "n": 142000
    },
    "300": {
      "name": "Greece",
      "rate": 0.66,
      "n": 21000
    },
    "380": {
      "name": "Italy",
      "rate": 0.71,
      "n": 33000
    },
    "578": {
      "name": "Norway",
      "rate": 0.34,
      "n": 9000
    },
    "642": {
      "name": "Romania",
      "rate": 0.45,
      "n": 4000
    },
    "752": {
      "name": "Sweden",
      "rate": 0.4,
      "n": 38000
    },
    "826": {
      "name": "United Kingdom",
      "rate": 0.58,
      "n": 24000
    }
  },
  "label_iso": [
    276,
    752,
    250,
    380,
    300,
    826,
    578
  ],
  "finding": "An Afghan was recognised 96% of the time in Germany but 40% in Sweden — same Refugee Convention."
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
    # choropleth: long table -> {vals: {numericISO: {name, rate, n?}}}.
    # mapping: {iso_col (ISO-3166-1 alpha-3), rate_col (0..1), name_col?, n_col?,
    #           label_iso? (list of alpha-3 codes to label)}.
    # The world-atlas TopoJSON keys features by NUMERIC ISO, so we translate
    # alpha-3 -> numeric via the embedded lookup (graceful: unmapped ISO dropped).
    ISO3_NUM = {
        "ROU":642,"HUN":348,"NOR":578,"FIN":246,"DNK":208,"SWE":752,"BEL":56,
        "TUR":792,"FRA":250,"GBR":826,"NLD":528,"IRL":372,"GRC":300,"ESP":724,
        "AUS":36,"CAN":124,"CHE":756,"ITA":380,"DEU":276,"TJK":762,"AUT":40,
        "POL":616,"CZE":203,"BGR":100,"SVN":705,"LUX":442,"LTU":440,"MLT":470,
        "ISL":352,"PRT":620,"HRV":191,"SVK":703,"EST":233,"LVA":428,"CYP":196,
        "USA":840,"NZL":554,"JPN":392,"KOR":410,"RUS":643,"UKR":804,
    }
    mp = scene.get("mapping", {}) or {}
    iso_col = mp.get("iso_col") or "iso"
    rate_col = mp.get("rate_col") or "rate"
    name_col = mp.get("name_col")
    n_col = mp.get("n_col")
    vals = {}
    for _, r in df.iterrows():
        iso = str(r[iso_col]).strip().upper()
        num = ISO3_NUM.get(iso)
        if num is None:
            continue
        try:
            rate = float(r[rate_col])
        except Exception:
            continue
        if pd.isna(rate):
            continue
        if rate > 1.0:            # tolerate 0..100 input
            rate = rate / 100.0
        entry = {"name": str(r[name_col]) if name_col and name_col in df.columns else iso,
                 "rate": round(rate, 4)}
        if n_col and n_col in df.columns and pd.notna(r[n_col]):
            try:
                entry["n"] = int(float(r[n_col]))
            except Exception:
                pass
        vals[num] = entry
    label_iso = [ISO3_NUM[c.strip().upper()] for c in (mp.get("label_iso") or [])
                 if c.strip().upper() in ISO3_NUM]
    out = {"vals": vals}
    if label_iso:
        out["label_iso"] = label_iso
    if mp.get("finding"):
        out["finding"] = mp["finding"]
    return out
```

**Notes:** VALIDATED in headless Chrome (real world-atlas CDN atlas) on two scenes: (1) array highlight ['Germany'] + explicit label_iso, (2) string highlight 'Sweden' + empty label_iso (labels all valued) + d.finding fallback. Both rendered 177 country paths, correct cobalt-ramp fills, direct labels with paper halo, ink-stroke outline on the highlighted country, sequential legend + no-data swatch, and the serif annot finding — zero JS console errors.

MOTION: fully screenshot-safe. All final geometry (paths, labels, legend) is drawn with its real attrs first; H.in only fades the <g> opacity 0->1. No width/r/dashoffset reveal. At t=0 the geometry is correct (Chrome --dump-dom with no virtual-time still showed full geometry).

extra_cdn: ONLY topojson-client is added (d3 is already in _SCAFFOLD). The world-atlas atlas itself is fetched at runtime via d3.json from CDN (default countries-110m.json) — NOT a <script>, so it is NOT in extra_cdn; override with d.atlas_url if you mirror it. If both the CDN fetch fails or topojson is missing, the renderer paints a graceful red annot message instead of throwing.

DATA KEYING (critical): vals MUST be keyed by NUMERIC ISO-3166-1 code (string or int both work — renderer does +id), because world-atlas feature.id is the numeric code, exactly like build_map.py's ISO_NUM table. The python_shaper handles alpha-3 -> numeric translation; if the agent passes inline data it must use numeric keys.

HIGHLIGHT: scene.highlight is matched against vals[*].name (NOT iso). Accepts a single string or an array. The matched country gets an ink (P.ink) outline + a larger signal-coloured clabel; everyone else stays on the neutral cobalt ramp with a small ink vlabel.

UNIQUE GRADIENT ID: each render uses a random uid for its <linearGradient>, so multiple choropleth scenes on one page won't collide.

scene._i is NOT relied upon (the driver doesn't set it). value_label drives the legend heading. Caption/eyebrow/lede are handled by the scaffold driver, not the renderer.

The renderer ignores 'frame' winding concerns by using a MultiPoint of 4 corners (faithful to the reference) — change d.frame to reframe to a different region (e.g. a wider Eurasia box).

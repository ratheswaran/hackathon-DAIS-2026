# Recipe — choropleth

**Data shape** (`scene.data`):
d = {
  vals: { <numericISO(int)>: { name: string, rate: number(0..1), n?: number } },  // REQUIRED. Keyed by the area's numeric feature id because the atlas TopoJSON features are keyed by feature.id = numeric code. For a country-level world atlas this is the ISO-3166-1 *numeric* code (e.g. India = 356); for an India states/districts atlas use whatever numeric id keys its features. e.g. {356:{name:"India",rate:0.34,n:9953}}.
  label_iso?: number[],   // optional list of numeric feature ids to direct-label on the map. If omitted/empty, ALL valued areas are labelled.
  frame?: [[lon,lat],...], // optional 4 corner points for the MultiPoint frame. For India pass [[68,6],[97,6],[97,37],[68,37]] (the renderer's built-in default frame may target a different region — set this explicitly for India).
  finding?: string,        // optional inline serif finding annotation; only used if scene.annotations[0] is absent.
  atlas_url?: string       // optional override for the atlas TopoJSON URL (e.g. an India states/districts TopoJSON you mirror).
}
// Scene meta consumed: scene.title (aria), scene.value_label (legend heading, default "indicator rate"),
// scene.highlight (string name OR array of names -> accented label + ink-stroke outline),
// scene.annotations[0] (preferred serif finding text).

**Minimal sample** (`scene.data`):
```json
{
  "atlas_url": "<your India states/districts TopoJSON URL>",
  "vals": {
    "1": {
      "name": "Kerala",
      "rate": 0.84,
      "n": 410
    },
    "2": {
      "name": "Maharashtra",
      "rate": 0.55,
      "n": 980
    },
    "3": {
      "name": "Tamil Nadu",
      "rate": 0.62,
      "n": 720
    },
    "4": {
      "name": "Madhya Pradesh",
      "rate": 0.34,
      "n": 510
    },
    "5": {
      "name": "Uttar Pradesh",
      "rate": 0.29,
      "n": 1480
    },
    "6": {
      "name": "Rajasthan",
      "rate": 0.31,
      "n": 460
    },
    "7": {
      "name": "Bihar",
      "rate": 0.18,
      "n": 320
    },
    "8": {
      "name": "Odisha",
      "rate": 0.27,
      "n": 240
    }
  },
  "label_iso": [
    1,
    2,
    3,
    4,
    5,
    7
  ],
  "frame": [[68, 6], [97, 6], [97, 37], [68, 37]],
  "finding": "Facility coverage ran 0.84 in Kerala but 0.18 in Bihar — the same national health system."
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
    # choropleth: long table -> {vals: {numeric_feature_id: {name, rate, n?}}}.
    # mapping: {iso_col, rate_col (0..1), name_col?, n_col?,
    #           label_iso? (list of feature codes to label)}.
    # COUNTRY-LEVEL atlas case (world-atlas): features key by NUMERIC ISO, so we
    # translate alpha-3 -> numeric via the embedded lookup (graceful: unmapped dropped).
    # INDIA SUB-NATIONAL case (states/districts atlas): the atlas keys features by
    # its own numeric id — pass numeric `iso_col` values that match feature.id and
    # this lookup is bypassed (codes already numeric strings fall through unmapped,
    # so for that case key `vals` directly when hand-authoring `data`).
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

**Notes:** VALIDATED in headless Chrome (real world-atlas CDN atlas) on two scenes: (1) array highlight + explicit label_iso, (2) string highlight + empty label_iso (labels all valued) + d.finding fallback. Both rendered the atlas paths, correct cobalt-ramp fills, direct labels with paper halo, ink-stroke outline on the highlighted area, sequential legend + no-data swatch, and the serif annot finding — zero JS console errors. (Validation used the country-level world atlas; for the India states/districts case mirror an India TopoJSON and pass its URL via d.atlas_url + numeric feature-id keys.)

MOTION: fully screenshot-safe. All final geometry (paths, labels, legend) is drawn with its real attrs first; H.in only fades the <g> opacity 0->1. No width/r/dashoffset reveal. At t=0 the geometry is correct (Chrome --dump-dom with no virtual-time still showed full geometry).

extra_cdn: ONLY topojson-client is added (d3 is already in _SCAFFOLD). The world-atlas atlas itself is fetched at runtime via d3.json from CDN (default countries-110m.json) — NOT a <script>, so it is NOT in extra_cdn; override with d.atlas_url if you mirror it. If both the CDN fetch fails or topojson is missing, the renderer paints a graceful red annot message instead of throwing.

DATA KEYING (critical): vals MUST be keyed by the atlas's NUMERIC feature id (string or int both work — renderer does +id). For the country-level world atlas that is the numeric ISO-3166-1 code; for an India states/districts atlas it is whatever numeric id keys its features. The python_shaper handles alpha-3 -> numeric translation for the country case; if the agent passes inline data it must use the matching numeric keys.

HIGHLIGHT: scene.highlight is matched against vals[*].name (NOT iso). Accepts a single string or an array. The matched country gets an ink (P.ink) outline + a larger signal-coloured clabel; everyone else stays on the neutral cobalt ramp with a small ink vlabel.

UNIQUE GRADIENT ID: each render uses a random uid for its <linearGradient>, so multiple choropleth scenes on one page won't collide.

scene._i is NOT relied upon (the driver doesn't set it). value_label drives the legend heading. Caption/eyebrow/lede are handled by the scaffold driver, not the renderer.

The renderer ignores 'frame' winding concerns by using a MultiPoint of 4 corners (faithful to the reference) — change d.frame to reframe to a different region (e.g. the India bbox [[68,6],[97,6],[97,37],[68,37]], or a tighter state/district box).

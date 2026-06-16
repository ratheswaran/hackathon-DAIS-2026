# Medical Desert Planner — India (D3 map)

A self-contained, offline D3 map for the DAIS-for-Good 2026 **Medical Desert
Planner** track. It reimagines the Virtue Foundation "VF Match" globe (Africa
heat-hex + "Insight Layers" panel) as a **district-level India access-gap planner**
driven entirely by **our verified gap-analysis numbers**.

Open `india_medical_deserts.html` in any browser — no server, no internet, no build
step needed (d3 v7 + simplified boundaries + data are inlined; ~1.6 MB).

> Loading from `file://` works in most browsers. If a browser blocks the inline
> data, serve the folder: `python3 -m http.server 8755` then open
> `http://localhost:8755/india_medical_deserts.html`.

## What it shows

- **Choropleth of 641 districts** (638 painted, **99.5%**), switchable across 6 layers
  (the "Insight Layers" panel, right): **Medical Desert Risk** (default), Health Burden
  (HBI), Coverage gap, **Facility coverage** (red = 0 mapped facilities → green =
  covered), Distance to nearest facility, Maternal need.
- **9,953 facility points** on a canvas overlay — the deserts *are* the empty red
  expanses. Toggle on/off; colour by public/private.
- **Specialty lens** (dropdown) — filters the dots to facilities reporting a given
  specialty (e.g. Oncology → 1,856 facilities), exposing **specialty-specific deserts**.
  This mirrors VF Match's "General Surgery" selector.
- **Histogram range filters** (drag to brush) for HBI, mapped-facility count, and
  km-to-nearest — VF Match's signature mini-histogram sliders, reimagined to *dim*
  out-of-range districts.
- **Priority Deserts** ranked list (left) — top-30 by composite risk, click to fly-to
  + see a district detail card. **National stat callouts** above it.
- **Hover tooltip** with per-district risk / burden / facilities / distance / anaemia.
- Honesty caveats baked into the panel (sample not census, no per-capita, self-reported
  claims, suppression = rarity, Census-2011 boundaries).

## Headline numbers (computed at build time, all from our verified tables)

251 districts with zero mapped facilities · 210 true spatial deserts ·
median 16.6 km to the nearest facility · 100 high-maternal-need districts with zero
facility · Bihar HBI 79.4 vs Kerala 18.0 · 9,953 facilities mapped (a sample).

## Files

| File | What |
|---|---|
| `india_medical_deserts.html` | **The deliverable** — open this. |
| `template.html` | HTML/CSS/D3 app shell with `/*__D3__*/` + `/*__DATA__*/` injection points. |
| `build_map_data.py` | Reproducible build: joins our district tables into the geojson, simplifies geometry, builds facility/specialty layers + stats, inlines d3, writes the HTML. |
| `assets/d3.v7.min.js` | d3 v7.9 (inlined into the build). |
| `assets/india_districts.geojson` | DataMeet Census-2011 district boundaries (CC-BY 2.5). |
| `assets/datameet_LICENSE_readme.md` | DataMeet attribution / licence. |
| `DECISION_dataset_replacement.md` | Answer to "do we replace our dataset with Nikita's cleaned one?" (no — adopt the geojson + name-normalisation only). |

## District-name resolution (the PIN-crosswalk fix)

DataMeet boundaries are **Census-2011**; NFHS-5 uses ~2019 districts. The build
resolves each polygon to NFHS data in four tiers: exact + curated alias →
fuzzy-within-state → unique district-only → **spatial**: post-2011 split districts
are located by their pincode centroid (point-in-polygon) onto their 2011 **parent**
polygon and **survey-women-weighted aggregated** (e.g. Mahbubnagar ← Jogulamba Gadwal
+ Mahabubnagar + Nagarkurnool + Wanaparthy). Aggregated polygons are flagged in the
tooltip/detail. Result: **638/641 painted (99.5%)**; the 3 greys have no NFHS
counterpart (J&K "Data Not Available", Mizoram Saiha, Meghalaya Jaintia Hills) and
are shown honestly, not fabricated.

## Rebuild

```bash
python3 build_map_data.py     # needs pandas, pyarrow, shapely
```

Reads the gap-analysis parquet tables from
`../hackathon-session-2026-06-15/gap_analysis/out/` (gitignored session archive) and
the OHE specialty columns from a local clone of the teammate repo at
`/tmp/nikita-hackathon` (optional — only powers the specialty filter).

## Data lineage

Virtue Foundation `facilities` + `nfhs_5_district_health_indicators` +
`india_post_pincode_directory` → our verified gap-analysis tables
(`district_risk_index`, `spatial_desert_*`, `district_master`,
`gapD_district_clusters`) → joined onto DataMeet district boundaries (from teammate
`NikitaKrotenko/Hackathon`, the one asset worth lifting). Specialty tags via the
teammate's one-hot columns joined on `unique_id`.

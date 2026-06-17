# Do we replace our dataset with Nikita's cleaned one?

**Short answer: No — keep our analytical base. Selectively adopt two assets from
his repo (already done in this build): the DataMeet district-boundary geojson and
the state-name normalisation map. Do *not* import his cleaned NFHS or facilities
tables.**

Repo analysed: `github.com/NikitaKrotenko/Hackathon` @ `32d6286` (PR #2 "Data
preparation", merged to `main`). It contains `data/processed/{facilities,
health_indicators,postcodes_cleaned}.csv`, an `EDA.ipynb`, an
`external-datasets-recommendations.md`, and a **React/Leaflet** `india-health-map/`
app carrying a clean **DataMeet `india_districts.geojson`** (641 districts, CC-BY 2.5).

## Why not replace

| Their table | What they did | Why it's a downgrade for *our* analysis |
|---|---|---|
| `health_indicators.csv` (706×109) | Cleaned NFHS, then **median-imputed every missing/suppressed cell** | This is the dealbreaker. Our verified finding `R-nfhs-suppression-rarity-not-poverty` shows NFHS `*`-suppression encodes **rarity, not absence** (suppression↔HBI ρ≈−0.61, the "double-penalty" intuition was *falsified*). Median imputation **fabricates** values into exactly the cells that carry signal — it would silently contaminate the risk index, the confounder OLS, and the maternal-desert flags. |
| `facilities.csv` (10,088×105) | Kept `unique_id, numberDoctors, capacity, lat/lon` + **100 one-hot specialty columns**; **dropped name, address, pincode, district, state** | Throws away the **join spine**. Our spatial-desert work needs facility→pincode→district. Their file can't be joined to NFHS without re-deriving district from lat/lon. It is *also* not deduped (11 known dup `unique_id`) and leaves 6 out-of-India coordinates in place. Our `facilities_clean.parquet` (9,989 deduped, district+pin+trust+claims) is strictly richer. |
| `postcodes_cleaned.csv` (118,337) | `to_numeric` coerce, drop lat<2, dropna, dedup on lat/lon | Reasonable bronze cleaning, but **post-office grain** (not pincode grain) and it discards rows. We already crosswalk from the full 165,627-row raw directory. No reason to switch. |
| "load management model" | **Does not exist** — Discord said "tomorrow"; the OHE columns are scaffolding only | Nothing to adopt. |
| district **population** | Unsolved (only `households_surveyed` ≈870/district, which ≠ population) | Same blocker we already documented. Neither dataset enables per-capita. |

Net: their processing is competent **bronze-layer** work, but our gap-analysis
tables (`district_master`, `district_risk_index`, `spatial_desert_*`,
`gapD_district_clusters`, confounder OLS, logistic model, bootstrap CIs) are a
**silver/gold** layer they have not built. Replacing ours with theirs is a step backward.

## What we DID adopt (the genuinely valuable parts)

1. **`india_districts.geojson`** (DataMeet, Census-2011, CC-BY 2.5) — the boundary
   file we previously flagged as *missing*. It unlocks the choropleth. Bundled at
   `assets/india_districts.geojson` (attribution in `assets/datameet_LICENSE_readme.md`).
   Join coverage to our 706 NFHS districts: **99.5%** (638/641) via a 4-tier resolver
   (exact + alias → fuzzy → district-only → spatial parent-aggregation using the PIN
   crosswalk). Only 3 polygons with no NFHS counterpart stay grey, labelled honestly.
2. **State-name normalisation / alias map** — lifted from his `App.tsx` and extended
   with district-level spelling fixes (Barddhaman→Bardhaman, Garhchiroli→Gadchiroli,
   Marigaon→Morigaon, …). Lives in `build_map_data.py`.
3. **OHE specialty columns** from his `facilities.csv` — reused (joined on `unique_id`)
   to power the map's **specialty-lens dot filter** (e.g. "1,856 of 9,953 facilities
   report Oncology"). This is the one place his facilities file adds something ours lacks.

## Recommendation for the team

- Treat his repo as the **boundary-geometry + specialty-tagging** contributor, and our
  session archive as the **analytics** contributor. Don't merge the NFHS/facilities CSVs.
- If we want his OHE specialties in the warehouse, join them onto our
  `facilities_clean` by `unique_id` (keep our address/district columns), don't swap.
- His `external-datasets-recommendations.md` (National Hospital Directory, LGD
  village↔PIN crosswalk, Census population) is a good **enrichment roadmap** — the LGD
  crosswalk in particular would fix the 107 doubly-invisible districts and is worth pulling.

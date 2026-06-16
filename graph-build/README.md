# find_skill graph brain — REBUILT for India healthcare (Medical Desert Planner)

**Date:** 2026-06-15 · **Track:** Medical Desert Planner (DAIS-for-Good 2026, Virtue Foundation)
**Aura:** `neo4j+s://your-aura-instance.databases.neo4j.io`
**Embeddings:** `databricks-gte-large-en` (1024-dim) via the **event** workspace (`hackathon` CLI profile)

**Credentials** are read at runtime from the environment, never hardcoded. Set
`NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` directly, or point
`NEO4J_CREDS_FILE` at a **gitignored** local KEY=VALUE creds file (the Aura "download
credentials" `.txt` works as-is). The Databricks embed token comes from
`~/.databrickscfg [<DATABRICKS_PROFILE or "hackathon">]`. The repo root is inferred
repo-relative (override with `HACKATHON_REPO_ROOT`).

The prior (rehearsal) domain was **wiped and replaced** with the India healthcare domain. The
capability/skill layer (Tools, ChartRecipes, ChartTypes, SlideTypes, DeckGuides,
DesignRules, Assets) was **kept** — only the domain knowledge changed.

## Final graph (verified)

- **418 nodes**, all embedded (1024-dim); **785 typed edges + 2,465 kNN `SIMILAR_TO`**; 5 indexes ONLINE.
- **Domain (125):** 1 Domain, 1 GenieSpace, 3 Tables, 25 Columns, 15 Metrics, 19 Rules, 14 SqlPatterns, 14 Findings, 17 Questions, 16 new map/health DesignRules.
- **Skills kept (293):** 138 DesignRule, 49 Asset, ChartRecipe 36, DeckGuide 25, ChartType 21, SlideType 13, Tool 10.
- `find_skill` verified on 8 Medical-Desert probes — every probe routes to **"India Healthcare Access Space"** and seeds the right SqlPattern/Finding/Rule/DesignRule (see `verify_graph.py`).

## Pipeline (reproducible)

```bash
# from this graph-build/ dir; PY = a venv with neo4j, networkx, numpy, yaml, databricks.sdk
PY=../hackathon-orchestrator-neo4j/.venv-test/bin/python
cd graph-build
$PY build_domain_seed.py        # static structure + build_domain_dynamic.py -> domain_seed.json (125 nodes)
$PY run_build.py                # WIPE Aura + load domain_seed.json + skill_nodes.json (293) + embed (batch=64)
# ^ embed step 429s out on Free-Edition gte-large-en (inputs-per-request limit). If so:
$PY embed_finish.py             # decoupled embed at BATCH=1 (~11 min) + vector index + pagerank/louvain
$PY apply_increment.py          # R-facility-dedup rule + kNN SIMILAR_TO (explorer) + recompute analytics
$PY verify_graph.py             # acceptance test: ontology audit + 8 find_skill probes
```

Source-of-truth files:
- `build_domain_dynamic.py` — the authored domain (Metrics/Rules/SqlPatterns/Findings/Questions/DesignRules + all edges). Numbers are from the **source-verified EDA** (`eda_result.json`: 36 findings, 20 confirmed / 7 corrected / 0 rejected). Corrected numbers were applied.
- `skill_nodes.json` — the kept capability layer (exported from the prior graph, prior-domain artifacts filtered out).
- the 5 EDA analyst reports (supply/demand/desert/trust/quality) — methodology + reproducible code, summarized in `eda_result.json`.

## Key honesty contract (baked into the graph as Rules/DesignRules)

`facilities` is a **~10k web-scraped SAMPLE, not a census** (India's FDR lists 47k+). Facility counts =
**dataset coverage**, never absolute supply. No per-capita (no population in the 3 tables). Facility
capability fields are **self-reported scraped claims** — cite the source TEXT field, never assert as verified.

## Headline verified findings (the demo spine)

- **The Care Lottery:** district health access varies up to **81.5x** within India (insurance 1.2→97.8%, 4+ANC 4.4→98.7%).
- **Medical deserts:** **~245 of 698 NFHS districts (35%) have ZERO facilities** in this dataset; the 5 worst child-anaemia districts (Leh/Ladakh 95.5%, Sukma 91.4%, Lahul&Spiti 91.0%, Dantewada 89.9%, Tawang 89.6%) **all** have zero.
- **Supply ≠ need:** burden vs coverage Spearman ρ ≈ **−0.2 to −0.27 (p<1e-8)**; high-burden tertile averages 5.5 facilities vs ~14.6.
- **Burden belt:** Bihar HBI 78.4 vs Kerala 16.9 (4.6x); Araria (Bihar) worst district (89.7); 13/15 worst deserts in Bihar/Jharkhand.
- **Trust gap:** facility claims ~99% present but proof thin (doctors 36%, capacity 25%); median trust 45/100; **1,219 facilities (29.9% of advanced-claimers)** advertise MRI/CT/ICU/cancer with zero hard proof.
- **Dedup:** `facilities.unique_id` is NOT unique — 11 byte-identical dup rows → **9,989 distinct** (DISTINCT unique_id before counting).

## NEXT (orchestrator fork → event workspace)

1. **Create ONE Genie space** over the 3 tables (`databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.*`) on the `hackathon` workspace, then patch its real id into the GenieSpace node — no rebuild:
   ```cypher
   MATCH (g:Node {id:'GenieSpace:india_healthcare_access_space'}) SET g.space_id='<REAL_ID>';
   ```
   (then re-embed that one node so the id is in its embed_text, or leave — id is in `content` already).
2. Fork `hackathon-orchestrator-neo4j/` into this session, repoint `NEO4J_*` (secret scope) + `LLM_ENDPOINT_NAME=gpt-5-external-provider` + embeddings to the event workspace, deploy (Free-Edition 2-endpoint cap).
3. Build the app (fork `pudding-chatbot` / AppKit) with the graph-viz explorer (`kg/export_explorer.py`).

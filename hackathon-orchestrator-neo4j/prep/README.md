# Day-of dataset prep kit

The DAIS "Apps & Agents for Good" hackathon dataset is **gated until the event
starts** (Jun 15, 08:00 PT) — the template's own prerequisites say *"Details on
how to add the dataset will be available when the hackathon starts."* So you
cannot profile the real data today. What you **can** do today is build the
machinery that turns the two slowest day-of tasks — *understanding a mystery
dataset* and *standing up the knowledge graph over it* — into minutes.

This kit is **dataset-agnostic**. It runs against whatever catalog drops on the day.

```
prep/
  profile_catalog.py   # 1. any UC catalog  -> profile JSON + Markdown
  graph_seed.py        # 2. profile         -> graph_seed.json + skill_draft.md + findings_skeleton.json
  seed_load.py         # 3. seed (+ enrichment) -> loaded, embedded, indexed Neo4j graph
  _common.py           # shared config + SQL-warehouse execution
```

## The 3 steps (on event day)

### 1 · Profile the dataset
```bash
python -m prep.profile_catalog --catalog dais_2026 --out prep/out
```
Captures, per table: row count, dtypes, null %, ~cardinality, min/max, top
categorical values, sample rows. Across the catalog: **candidate join keys** and
**string-numeric "CAST before aggregating" gotchas** (e.g. NFHS percentage columns stored as text).
Writes `profile_<catalog>.json` (machine) + `.md` (read it first).

### 2 · Seed the knowledge graph
```bash
python -m prep.graph_seed --profile prep/out/profile_dais_2026.json
```
Deterministically turns the profile into the **data-semantics layer** of the
find_skill graph — `Domain / GenieSpace / Table / Column / Rule` nodes + their
edges — as `graph_seed.json` (the exact `{nodes, edges}` shape the extractor
pipeline and `seed_load.py` ingest). Also writes:
- `skill_draft.md` — fill the TODOs: **Metrics, verbatim SqlPatterns, Findings**.
- `findings_skeleton.json` — 6 "for Good" insight lenses to instantiate.

> The graph is your differentiator. The seed gives you the boring 60%
> (tables/columns/gotchas) for free so you spend day-of time on the **insight**.

### 3 · Load it into Aura
```bash
# structural dry-run first (no embeddings, no wipe):
python -m prep.seed_load --seed prep/out/graph_seed.json --no-embed

# real load (embeds via databricks-gte-large-en, builds kg_embeddings/kg_fulltext):
python -m prep.seed_load --seed prep/out/graph_seed.json --wipe

# then add the enriched skill/findings nodes you authored:
python -m prep.seed_load --seed prep/out/graph_seed.json --also prep/out/my_patterns.json
```
Loads with the **same embeddings + indexes find_skill uses at runtime** (reuses
the orchestrator's `brain/`), so `find_skill` works immediately:
```bash
python -m brain.kg_retrieve "which X has the most Y, and how to chart it"
```

## Two things to fill that the profile can't infer
1. **Genie `space_id`** — create the Genie Space(s) on the day, paste the real
   id into the `GenieSpace` node (seed ships `REPLACE_WITH_SPACE_ID_ON_EVENT_DAY`).
   A blind route = the agent burning calls guessing the space.
2. **The "why"** — one honest, CI-backed disparity/insight beats ten dashboards.
   That's `findings_skeleton.json` + the SqlPattern that proves it.

## Config
Reads `workspace_config.yml` (`databricks.host/token`, `compute.sql_warehouse_id`,
`unity_catalog.catalog`, `neo4j.*`). Every value is env-overridable
(`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `SQL_WAREHOUSE_ID`, `HACKATHON_CATALOG`,
`NEO4J_URI/USER/PASSWORD/DATABASE`). Read-only against the warehouse.

## Rule 4.2(d) note
The submission repo must be built **during** the Project Period. Treat this kit
as a **reusable library you run on the day**, not pre-written project code — and
ideally publish it as a standalone open-source repo before the event so it's
unambiguously a tool, not the submission. Confirm the interpretation on Discord.
```bash
python -m py_compile prep/*.py   # smoke check
```

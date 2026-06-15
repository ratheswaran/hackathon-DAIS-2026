# DAIS for Good 2026 — India Healthcare Access / Medical Desert Planner

A full-stack data-analytics agent for the **Virtue Foundation India healthcare-access** dataset,
built on Databricks for the **Data + AI Summit for Good 2026** hackathon (track: *Medical Desert Planner*).

The agent answers natural-language questions about healthcare **access gaps** — districts with high
health burden but few nearby facilities — and produces decks, scrollytelling data stories, and notebooks.

## Architecture

| Component | What it does |
|-----------|--------------|
| `hackathon-orchestrator-neo4j/` | DeepAgents orchestrator (Databricks Model Serving). A **Neo4j knowledge-graph** `find_skill` tool routes every request to the right Genie space, SQL pattern, metric, finding, and chart/deck recipe — the graph **is** the domain knowledge. Includes the graph-retrieval code in `brain/`. |
| `nodejs-app-v3/` | React/Express chat UI (Databricks App). SSE streaming → Model Serving endpoint. Persistent chat history in Lakebase. |
| `hackathon-skills/` | Domain + design-system skill files (the filesystem fallback; the live system uses the graph). |
| `graph-build/` | Reproducible pipeline that builds the India-healthcare `find_skill` graph (domain seed + capability/skill layer + embeddings) on Neo4j Aura. |

## Data

Virtue Foundation Delta Share — `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset`:
`facilities` (~10k web-discovered **sample**, not a census), `india_post_pincode_directory` (PIN→district),
`nfhs_5_district_health_indicators` (706 districts × 109 metrics).

**Honesty contract** (baked into the agent): facilities is a sample → report *coverage*, never absolute supply;
no population denominator → no per-capita rates; facility capability fields are self-reported claims.

## Stack

Databricks Model Serving (gpt-5.5 via Azure) · Genie Spaces · Lakebase (Autoscale Postgres) ·
Neo4j Aura (knowledge graph) · `databricks-gte-large-en` embeddings · DeepAgents + LangGraph · React/Vite + Express.

## Secrets

No credentials are committed. The orchestrator reads them from a Databricks secret scope / a gitignored
`workspace_config.yml` (see `hackathon-orchestrator-neo4j/workspace_config.example.yml`); the app reads
`POSTGRES_URL` / `DATABRICKS_SERVING_ENDPOINT` from app env. Placeholders like `${LAKEBASE_PASSWORD}`
and `${NEO4J_PASSWORD}` mark where to supply your own.

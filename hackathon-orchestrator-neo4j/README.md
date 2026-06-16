# hackathon-orchestrator-neo4j

A DeepAgents orchestrator that is **byte-for-byte the production hackathon
orchestrator except for ONE thing**: the filesystem skills folder is replaced by
a **Neo4j llm-wiki knowledge graph**, queried through a single `find_skill` tool.

Everything else is unchanged — the two subagents (python-analyst, data-viz),
the Genie data path, `compose_infographic` / `compose_deck` / `compose_document`,
the Lakebase memory (checkpointer + chat history + user preferences), the
prompts' voice/rules/formatting, and `gpt-5.5` on Model Serving. It runs
**parallel** to the live orchestrator: new serving endpoint, new Databricks Apps
URL, same workspace.

## Why

The production agent discovers skills by **progressive disclosure**: DeepAgents'
`SkillsMiddleware` injects every `SKILL.md` overview into the system prompt, and
the agent walks `/skills/` with `read_file` (6+ round-trips, ~13k tokens). This
fork replaces that with **one graph traversal** that returns a *plan* — and the
graph isn't a file index, it's the knowledge itself (the llm-wiki pattern: atomic
concept *pages-as-nodes* with typed relationships).

```
                      PRODUCTION                         THIS FORK
  skill lookup   SkillsMiddleware + read_file walk   find_skill → 1 graph traversal
  knowledge      .md files on a FilesystemBackend     Neo4j graph (Aura Free)
  the agent...   reads files to assemble context      reads a PLAN (no files)
```

## What `find_skill(query)` returns

A **plan**, assembled by seeding on the most relevant nodes (vector + fulltext
over node content) and expanding one hop along the answer-path relations:

- **Route to Genie** — the right Genie Space + its real `space_id`
- **SQL pattern** — the verbatim SQL to run
- **Gotchas to honor** — the rules/casts (PIN→district join, facilities is a sample, NFHS try_cast…)
- **Metric** — the definition/formula
- **Visualize with** — the chart recipe / chart type + which tool (`compose_infographic` / `compose_deck`)
- **Why / insight** — the analytical finding (district access gap, zero-facility deserts, urbanisation confounder)
- **Relationships** — the edges connecting them (so the agent sees *why* they connect)

No skill files are read. The graph **is** the knowledge source.

## The knowledge graph (llm-wiki-as-graph)

Built by `neo4j/hackathon-brain/kg/` — LLM extractors disassemble the skills
`.md` + the EDA/findings analysis into a typed graph:

- **18 node types** across 3 layers — data-semantics (`Domain`, `GenieSpace`,
  `Table`, `Column`, `Metric`, `Rule`), why/insight (`Finding`, `Question`), and
  capability (`SqlPattern`, `ChartType`, `ChartRecipe`, `DesignRule`, `SlideType`,
  `DeckGuide`, `Tool`, `Region`, `Asset`, `Concept`). Each node is an atomic
  "wiki page": its `content` is the self-sufficient text the agent needs.
- **25 edge types** — `ROUTES_TO`, `ANSWERS`, `COMPUTES`, `HONORS`, `GOTCHA_FOR`,
  `VISUALIZED_BY`, `PRODUCED_BY`, `SURFACES`, `ABOUT`, `EXPLAINS_WHY`, `JOINS_ON`…
- **Analytics** — PageRank (node centrality), Louvain communities, embedding kNN
  `SIMILAR_TO`. Computed offline with networkx → no GDS plugin → runs on **Aura Free**.
- Non-`.md` files (the `ra_template.pptx`, html scaffolds, fonts, css) become
  `Asset` nodes — *referenced* by path, not parsed; the tools still load them.

Embeddings: `databricks-gte-large-en` (1024-dim) on both sides (ingest + query),
so **no torch ships in the serving image** — `find_skill` makes one embed call
per query, the same pattern the existing semantic cache uses.

## Layout

```
deploy_orchestrator_agent.py   the agent (the find_skill swap is the only diff)
brain/                         vendored KG retrieval (kg_retrieve.py::kg_search) + driver/embed
tools/find_skill.py            the find_skill tool (traversal → plan + a graph-viz panel)
subagents/                     prompts (skill-access instructions point at find_skill)
skills/                        symlink → ../hackathon-skills (TOOL ASSETS only; agent reads none)
workspace_config.yml           creds + the neo4j: block  (gitignored; see .example.yml)
setup_neo4j_secrets.sh         put Neo4j creds in the agent-secrets scope (SAP pattern)
deploy.sh / DEPLOY.md          stage → push → submit → poll (parallel endpoint/app)

../neo4j/hackathon-brain/kg/   the KG builder (run once to (re)build the graph):
  ontology.py                  the 18-node / 25-edge schema (the extractor contract)
  extract_workflow.js          37 LLM extractors + cross-link (run via the Workflow tool)
  merge_load.py                dedupe → load Aura → embed → analytics
  fragments/kg_raw.json        the extracted graph (reproducible build artifact)
```

## Build / deploy

```bash
# 1. Build the knowledge graph into Aura (one-time, ~15 min extraction + ~10 min embed)
#    - run kg/extract_workflow.js via the Workflow tool, save its result to kg/fragments/kg_raw.json
cd ../neo4j/hackathon-brain
NEO4J_URI=... NEO4J_USER=... NEO4J_PASSWORD=... NEO4J_DATABASE=... \
BRAIN_EMBED_BACKEND=databricks BRAIN_EMBED_ENDPOINT=databricks-gte-large-en BRAIN_EMBED_BATCH=1 \
DATABRICKS_HOST=... DATABRICKS_TOKEN=... \
  .venv/bin/python -m kg.merge_load

# 2. (prod) put Neo4j creds in the secret scope, then flip neo4j.inject_plaintext: false
./setup_neo4j_secrets.sh

# 3. deploy the parallel endpoint + app
./deploy.sh
```

See `DEPLOY.md` for the deploy ritual and `../DeepAgent Vault/wiki/guides/`
for the design write-up.

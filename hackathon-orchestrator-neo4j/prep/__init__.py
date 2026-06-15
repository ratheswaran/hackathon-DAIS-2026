"""Day-of dataset prep kit for the DAIS Apps & Agents for Good hackathon.

The hackathon dataset is gated until the event starts (Jun 15 08:00 PT); these
tools turn the two slowest day-of tasks into minutes:

  1. profile_catalog.py  — point at ANY Unity Catalog catalog -> a full profile
                           (schemas, tables, row counts, dtypes, null %,
                           cardinality, candidate join keys, string-numeric
                           "cast" gotchas, sample rows) as JSON + Markdown.

  2. graph_seed.py        — turn that profile into an ontology-valid
                           {nodes, edges} seed for the find_skill knowledge
                           graph + a skill_draft.md + a findings_skeleton.json
                           you flesh out with the insight/SQL layers.

  3. seed_load.py         — load the seed into Neo4j (Aura) using the
                           orchestrator's own brain/ modules, so the embeddings
                           and indexes (kg_embeddings / kg_fulltext) match what
                           find_skill expects at query time.

Nothing here is dataset-specific — it runs against whatever drops on event day.
See prep/README.md for the runbook.
"""

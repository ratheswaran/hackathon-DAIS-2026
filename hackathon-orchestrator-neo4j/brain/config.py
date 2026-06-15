"""Central configuration for the hackathon-skills Neo4j brain.

Everything is overridable by env var so the same code runs against the local
Docker Neo4j (default) or an Aura / NAMS-style remote instance later.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Neo4j connection -------------------------------------------------------
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "hackathonbrain")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# --- Embedding model --------------------------------------------------------
# Backend selects HOW chunks/queries are embedded:
#   "sentence-transformers" (default) — local all-MiniLM-L6-v2, 384-dim, needs
#                                        torch. Best for the offline benchmark.
#   "databricks"                       — Databricks FM embeddings endpoint
#                                        (default databricks-gte-large-en,
#                                        1024-dim). No torch → slim serving
#                                        image; the SAME endpoint is called at
#                                        ingest and inside find_skill at query
#                                        time. Needs DATABRICKS_HOST + _TOKEN.
EMBED_BACKEND = os.environ.get("BRAIN_EMBED_BACKEND", "sentence-transformers")
EMBED_MODEL = os.environ.get("BRAIN_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_ENDPOINT = os.environ.get("BRAIN_EMBED_ENDPOINT", "databricks-gte-large-en")
EMBED_BATCH = int(os.environ.get("BRAIN_EMBED_BATCH", "64"))
# Dimension MUST match the active backend (MiniLM=384, gte-large-en=1024).
# Defaults to 1024 when the databricks backend is selected unless overridden.
_default_dim = 1024 if EMBED_BACKEND == "databricks" else 384
EMBED_DIM = int(os.environ.get("BRAIN_EMBED_DIM", str(_default_dim)))

# --- Corpus -----------------------------------------------------------------
# The comprehensive skills folder we are converting into a graph. Resolved
# relative to this file so it works regardless of the caller's CWD.
_HERE = Path(__file__).resolve()
# Only used by the OFFLINE build pipeline (parse/ingest), never by find_skill
# retrieval. Resolved defensively so importing this module never crashes in the
# Model Serving artifact layout (where the path may be shallow).
try:
    PROJECT_ROOT = _HERE.parents[3]
except IndexError:
    PROJECT_ROOT = _HERE.parent
SKILLS_DIR = Path(os.environ.get("BRAIN_SKILLS_DIR", str(PROJECT_ROOT / "hackathon-skills")))

# --- Retrieval / analytics knobs -------------------------------------------
VECTOR_INDEX = "chunk_embeddings"
FULLTEXT_INDEX = "chunk_fulltext"
CONCEPT_FULLTEXT_INDEX = "concept_fulltext"

# Network-analytics backend:
#   "offline" (default) — compute PageRank/Louvain/kNN with networkx at ingest and
#                          write the results as node properties. Needs NO GDS plugin,
#                          so it runs on Aura Free (and any Neo4j). Best for a static corpus.
#   "gds"               — use the Neo4j GDS library (gds.pageRank/louvain/knn). Needs the
#                          plugin (self-hosted Community/Enterprise or Aura Professional).
#   "auto"              — use gds if gds.version() is available, else offline.
GDS_MODE = os.environ.get("BRAIN_GDS_MODE", "offline")

KNN_TOPK = 6            # SIMILAR_TO edges per chunk (kNN)
KNN_CUTOFF = 0.55       # min cosine similarity to keep a SIMILAR_TO edge
SEED_VECTOR_K = 8       # vector seeds per query
SEED_FULLTEXT_K = 8     # fulltext seeds per query
EXPAND_HOPS = 1         # graph expansion hops from seeds
RESULT_K = 6            # chunks returned to the "LLM"

# Blend weights for the final chunk score (see retrieve.py). All signals are
# normalised to 0..1 so the weights mean what they say. Semantics dominate;
# the network-analytics signals (pagerank/community) are precision boosters, NOT
# drivers — raw (un-normalised) pagerank causes hub bias toward the dense corpus
# cluster, which the benchmark caught and these weights correct.
W_VECTOR = 1.0          # semantic similarity to the query (cosine, 0..1)
W_CONCEPT = 0.5         # fraction of query concepts present via MENTIONS (0..1)
W_PAGERANK = 0.12       # concept-graph centrality, normalised (tie-breaker only)
W_COMMUNITY = 0.15      # same Louvain community as a strong vector seed
W_GRAPH_PROX = 0.05     # reachable from a seed (mild recall boost)

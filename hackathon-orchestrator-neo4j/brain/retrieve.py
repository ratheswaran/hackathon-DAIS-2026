"""The graph brain: answer 'which skill material is relevant to this query?'

One vector query + one fulltext query + graph expansion + network-analytics
re-rank, all in a SINGLE Cypher round-trip. Returns the minimal set of skill
chunks the agent should read, plus the routed skill folders.

Signal blend (weights in config):
  vector       semantic cosine of the query to the chunk
  concept      overlap of query concepts with chunk concepts, weighted by hubness
  pagerank     chunk sits on central (hub) concepts of the corpus
  community    chunk shares a Louvain community with a strong vector seed
  graph_prox   chunk is a seed or 1 hop from a seed (SIMILAR_TO / SHARES_CONCEPT)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import config, embed, extract
from .db import Neo4j

_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9]+")


@dataclass
class Hit:
    chunk_id: str
    skill: str
    doc_path: str
    breadcrumb: str
    score: float
    signals: dict
    text: str


@dataclass
class BrainResult:
    query: str
    hits: list[Hit]
    skills_routed: list[str]
    timings_ms: dict
    db_round_trips: int

    def payload_chars(self) -> int:
        return sum(len(h.text) for h in self.hits)


def _lucene(query: str) -> str:
    toks = [t.lower() for t in _TOKEN.findall(query) if len(t) > 2]
    # OR semantics (default); fuzzy on longer tokens to catch morphology
    return " ".join(f"{t}~1" if len(t) >= 5 else t for t in toks) or query.lower()


_BRAIN_CYPHER = """
// ---- seeds: semantic (vector) ----
CALL db.index.vector.queryNodes($vindex, $kv, $qvec) YIELD node AS vn, score AS vs
WITH collect({id: vn.id, s: vs}) AS V
// ---- seeds: lexical (fulltext) ----
CALL db.index.fulltext.queryNodes($ftindex, $ql, {limit: $kf}) YIELD node AS fn, score AS fs
WITH V, collect({id: fn.id, s: fs}) AS Fraw
WITH V, Fraw,
     reduce(m = 0.0, x IN Fraw | CASE WHEN x.s > m THEN x.s ELSE m END) AS fmax
WITH V,
     apoc.map.fromPairs([x IN V | [x.id, x.s]]) AS vmap,
     apoc.map.fromPairs([x IN Fraw | [x.id, CASE WHEN fmax > 0 THEN x.s/fmax ELSE 0.0 END]]) AS fmap
WITH vmap, fmap, [x IN keys(vmap)][0..$seedN] AS topSeedIds
// strong vector seeds -> their communities (for the community signal)
OPTIONAL MATCH (sc:Chunk) WHERE sc.id IN topSeedIds
WITH vmap, fmap, topSeedIds, collect(DISTINCT sc.community) AS seedComms

// ---- candidate generation: seeds + 1-hop neighbours + concept-linked ----
CALL (vmap, fmap, topSeedIds) {
  // a) every vector/fulltext seed
  UNWIND keys(apoc.map.merge(vmap, fmap)) AS sid
  MATCH (c:Chunk {id: sid}) RETURN c
  UNION
  // b) graph neighbours of the strong seeds
  MATCH (s:Chunk)-[:SIMILAR_TO|SHARES_CONCEPT]-(c:Chunk)
  WHERE s.id IN topSeedIds RETURN c
  UNION
  // c) chunks mentioning a concept the query mentions
  MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE k.name IN $qconcepts RETURN c
}
WITH DISTINCT c, vmap, fmap, topSeedIds, seedComms

// ---- per-candidate signals ----
OPTIONAL MATCH (c)-[:MENTIONS]->(k:Concept)
WITH c, vmap, fmap, topSeedIds, seedComms,
     collect(k) AS kc
WITH c, vmap, fmap, topSeedIds, seedComms,
     coalesce(vmap[c.id], 0.0) AS vscore,
     coalesce(fmap[c.id], 0.0) AS fscore,
     size([k IN kc WHERE k.name IN $qconcepts]) AS matched,
     reduce(p = 0.0, k IN kc | p + coalesce(k.pagerank, 0.0)) AS pr_raw,
     CASE WHEN c.community IN seedComms THEN 1.0 ELSE 0.0 END AS comm,
     CASE WHEN c.id IN topSeedIds THEN 1.0 ELSE 0.0 END AS is_seed,
     size(kc) AS nconcepts
// graph proximity: seed OR neighbour-of-seed
OPTIONAL MATCH (c)-[:SIMILAR_TO|SHARES_CONCEPT]-(nb:Chunk) WHERE nb.id IN topSeedIds
WITH c, vscore, fscore, matched, pr_raw, comm, is_seed, nconcepts,
     CASE WHEN is_seed = 1.0 OR count(nb) > 0 THEN 1.0 ELSE 0.0 END AS prox
WITH c, vscore, fscore, comm, prox,
     // fraction of the query's concepts present in this chunk (0..1)
     CASE WHEN $nqc > 0 THEN toFloat(matched) / $nqc ELSE 0.0 END AS concept_overlap,
     // mean normalised pagerank of this chunk's concepts (0..1)
     CASE WHEN nconcepts > 0 THEN pr_raw / nconcepts ELSE 0.0 END AS pagerank_sig
WITH c,
     ($wv * (0.7*vscore + 0.3*fscore)) +
     ($wc * concept_overlap) +
     ($wp * pagerank_sig) +
     ($wcomm * comm) +
     ($wprox * prox) AS final,
     vscore, fscore, concept_overlap, pagerank_sig, comm, prox
RETURN c.id AS chunk_id, c.skill_slug AS skill, c.doc_path AS doc_path,
       c.breadcrumb AS breadcrumb, c.text AS text, final,
       {vector: round(vscore,3), fulltext: round(fscore,3),
        concept: round(concept_overlap,3), pagerank: round(pagerank_sig,4),
        community: comm, graph_prox: prox} AS signals
ORDER BY final DESC
LIMIT $resultk
"""


def brain_search(
    db: Neo4j,
    query: str,
    result_k: int | None = None,
    embed_fn: Optional[Callable[[str], list]] = None,
) -> BrainResult:
    """One-round-trip vector+graph retrieval over the skills brain.

    ``embed_fn`` lets a caller inject its own query embedder (e.g. the
    orchestrator's ``DatabricksEmbeddings`` so the serving container's ambient
    auth is used). When None, falls back to the env-driven ``embed.encode_one``.
    """
    result_k = result_k or config.RESULT_K
    t_embed0 = time.time()
    qvec = embed_fn(query) if embed_fn is not None else embed.encode_one(query)
    qconcepts = sorted({name for name, _ in extract.extract_from_text(query)})
    t_embed = (time.time() - t_embed0) * 1000

    t_db0 = time.time()
    rows = db.run(
        _BRAIN_CYPHER,
        vindex=config.VECTOR_INDEX, ftindex=config.FULLTEXT_INDEX,
        qvec=qvec, ql=_lucene(query), qconcepts=qconcepts, nqc=len(qconcepts),
        kv=config.SEED_VECTOR_K * 3, kf=config.SEED_FULLTEXT_K * 3,
        seedN=config.SEED_VECTOR_K, resultk=result_k,
        wv=config.W_VECTOR, wc=config.W_CONCEPT, wp=config.W_PAGERANK,
        wcomm=config.W_COMMUNITY, wprox=config.W_GRAPH_PROX,
    )
    t_db = (time.time() - t_db0) * 1000

    hits = [Hit(chunk_id=r["chunk_id"], skill=r["skill"], doc_path=r["doc_path"],
                breadcrumb=r["breadcrumb"], score=round(r["final"], 4),
                signals=r["signals"], text=r["text"]) for r in rows]
    # routed skills = distinct skill folders of the hits, ranked by appearance
    routed: list[str] = []
    for h in hits:
        if h.skill not in routed:
            routed.append(h.skill)
    return BrainResult(query=query, hits=hits, skills_routed=routed,
                       timings_ms={"embed": round(t_embed, 1), "db": round(t_db, 1),
                                   "total": round(t_embed + t_db, 1)},
                       db_round_trips=1)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "what chart should I use to show recognition rate by country of origin"
    with Neo4j() as db:
        res = brain_search(db, q)
    print(f"\nQ: {q}")
    print(f"timings: {res.timings_ms}  round-trips: {res.db_round_trips}  payload: {res.payload_chars()} chars")
    print(f"skills routed: {res.skills_routed}\n")
    for i, h in enumerate(res.hits, 1):
        print(f"{i}. [{h.score}] {h.skill} :: {h.breadcrumb}")
        print(f"   signals: {h.signals}")
        print(f"   {h.text[:120].replace(chr(10),' ')}…\n")

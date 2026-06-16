"""Knowledge-graph traversal for find_skill — the llm-wiki-as-graph retrieval.

Unlike the chunk brain (which returned file chunks to read), this returns a
PLAN: from a user prompt it seeds on the most relevant nodes (vector + fulltext
over node content), expands ONE hop along the answer-path relations
(ROUTES_TO / ANSWERS / COMPUTES / HONORS / VISUALIZED_BY / PRODUCED_BY /
SURFACES / ABOUT …), and assembles which Genie space to query, the verbatim
SQL, the gotchas to honor, the metric, the chart/deck recipe + which tool, and
the "why" insight — all from node content, so the agent never reads a file.

Two small Cypher round-trips (seed+score, then expand+collect) inside one
find_skill call — still a fraction of the 6-round-trip read_file walk.

Token discipline (2026-06-10): expansion follows ONLY typed answer-path edges —
SIMILAR_TO (kNN) is deliberately excluded; on the live graph it contributed
~78 of ~138 expansion edges and tripled the plan to ~35k chars (~9k tokens),
the hub-bias lesson in a new costume. The plan is additionally budgeted:
per-section item caps + a global char budget (BRAIN_PLAN_BUDGET, default
7000 chars ≈ 1.75k tokens) enforced on the FINAL string incl. the
Relationships footer, seeds first (degrading to teasers past the budget,
never dropped), neighbours by pagerank.
"""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import config, embed, extract
from .db import Neo4j

_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9]+")

# Answer-path relations expanded from the seed nodes to build a plan.
# NO SIMILAR_TO here: kNN edges are for the viz/explorer, not the plan —
# expanding them floods the plan with semantically-near-but-irrelevant nodes.
_PLAN_RELS = [
    "ROUTES_TO", "ANSWERS", "COMPUTES", "MEASURED_BY", "HONORS", "GOTCHA_FOR",
    "VISUALIZED_BY", "PRODUCED_BY", "USES_CHART", "STYLED_BY", "USES_SLIDE",
    "SURFACES", "ABOUT", "EXPLAINS_WHY", "QUERIES", "SERVED_BY", "HAS_TABLE",
    "HAS_COLUMN", "DERIVED_FROM", "COMPUTED_FROM", "APPLIES_TO",
]
_REL_PATTERN = "|".join(_PLAN_RELS)

# Plan sections in priority order: (title, node kinds that feed it, max items).
# Caps keep one query's plan to the few highest-value pages per section;
# the agent can always re-call find_skill with a narrower query for more.
_SECTION_SPECS = [
    ("Route to Genie", ["GenieSpace"], 2),
    ("SQL pattern", ["SqlPattern"], 3),
    ("Gotchas to honor", ["Rule"], 5),
    ("Metric", ["Metric"], 3),
    ("Tables / columns", ["Table", "Column"], 4),
    # Deck before charts: SlideType/DeckGuide pages only enter via deck intent,
    # and when they do, the spec matters more than another chart recipe.
    ("Deck", ["SlideType", "DeckGuide"], 5),
    ("Visualize with", ["ChartRecipe", "ChartType"], 3),
    ("Design", ["DesignRule"], 3),
    ("Why / insight", ["Finding"], 3),
    ("Tools", ["Tool"], 2),
    ("Domain", ["Domain"], 1),
]

# Global plan budget in chars (~4 chars/token), enforced on the FINAL string
# (sections + Relationships footer). 9000→7000 in the 2026-06-12 opt round 2:
# plan tokens are replay-multiplied by every later LLM call in the loop, and a
# 3.8k-char plan proved sufficient for a full deck spec. Seeds always ship —
# past the budget they degrade to headline + teaser, never drop.
PLAN_BUDGET = int(os.environ.get("BRAIN_PLAN_BUDGET", "7000"))

# Deliverable-intent routes: when the query asks for a concrete deliverable,
# the data topic dominates the embedding and the capability pages (DeckGuide /
# SlideType / ChartRecipe / Tool) never seed. Detect the intent and pull the
# canonical Tool page + its spec neighbourhood deterministically — the same
# trick as the Domain router, but for the production side.
_INTENT_TOOLS = [
    (re.compile(r"\b(deck|pptx|power\s*point|slides?|presentation)\b", re.I),
     "Tool:compose_deck"),
    (re.compile(r"\b(infographic|data\s+story)\b", re.I),
     "Tool:compose_infographic"),
    (re.compile(r"\b(scrolly|scrollytelling)\b", re.I), "Tool:compose_story"),
    (re.compile(r"\b(word\s+doc|document)\b", re.I), "Tool:compose_document"),
    (re.compile(r"\bnotebook\b", re.I), "Tool:run_python_code"),
]

_INTENT_CYPHER = """
MATCH (t:Node) WHERE t.id IN $tids
OPTIONAL MATCH (t)-[r:PRODUCED_BY|USES_SLIDE|USES_CHART|STYLED_BY|APPLIES_TO]-(m:Node)
WHERE m.kind IN ['DeckGuide', 'SlideType', 'ChartRecipe', 'DesignRule']
WITH t, m, r ORDER BY coalesce(m.pagerank, 0.0) DESC
WITH t, collect({m: m, rel: CASE WHEN r IS NULL THEN null
        ELSE {a: startNode(r).id, t: type(r), b: endNode(r).id} END})[0..10] AS nbrs
RETURN t.id AS tid, t.kind AS tkind, t.name AS tname, t.content AS tcontent,
       round(coalesce(t.pagerank, 0.0), 4) AS tpr,
       [x IN nbrs WHERE x.m IS NOT NULL |
        {id: x.m.id, kind: x.m.kind, name: x.m.name, content: x.m.content,
         pagerank: round(coalesce(x.m.pagerank, 0.0), 4), rel: x.rel}] AS nbrs
"""


@dataclass
class KgNode:
    id: str
    kind: str
    name: str
    content: str
    pagerank: float
    score: float
    signals: dict
    is_seed: bool


@dataclass
class KgResult:
    query: str
    nodes: list[KgNode]
    edges: list[dict]
    timings_ms: dict
    db_round_trips: int

    def payload_chars(self) -> int:
        return sum(len(n.content) for n in self.nodes)


def _lucene(query: str) -> str:
    toks = [t.lower() for t in _TOKEN.findall(query) if len(t) > 2]
    return " ".join(f"{t}~1" if len(t) >= 5 else t for t in toks) or query.lower()


_SEED_CYPHER = """
CALL db.index.vector.queryNodes('kg_embeddings', $kv, $qvec) YIELD node AS vn, score AS vs
WITH collect({id: vn.id, s: vs}) AS V
CALL db.index.fulltext.queryNodes('kg_fulltext', $ql, {limit: $kf}) YIELD node AS fn, score AS fs
WITH V, collect({id: fn.id, s: fs}) AS Fr
WITH V, Fr, reduce(m = 0.0, x IN Fr | CASE WHEN x.s > m THEN x.s ELSE m END) AS fmax
WITH apoc.map.fromPairs([x IN V | [x.id, x.s]]) AS vmap,
     apoc.map.fromPairs([x IN Fr | [x.id, CASE WHEN fmax > 0 THEN x.s/fmax ELSE 0.0 END]]) AS fmap
WITH vmap, fmap, [k IN keys(vmap)][0..$seedN] AS seedIds
UNWIND keys(apoc.map.merge(vmap, fmap)) AS cid
MATCH (c:Node {id: cid})
WITH c, seedIds,
     coalesce(vmap[c.id], 0.0) AS vscore,
     coalesce(fmap[c.id], 0.0) AS fscore,
     CASE WHEN c.id IN seedIds THEN 1.0 ELSE 0.0 END AS is_seed
WITH c, vscore, fscore, is_seed,
     ($wv * (0.7*vscore + 0.3*fscore)) + ($wp * coalesce(c.pagerank, 0.0)) + ($wseed * is_seed) AS final
ORDER BY final DESC
LIMIT $resultk
RETURN collect({id: c.id, kind: c.kind, name: c.name, content: c.content,
                pagerank: round(coalesce(c.pagerank, 0.0), 4), score: round(final, 4),
                is_seed: is_seed,
                signals: {vector: round(vscore,3), fulltext: round(fscore,3),
                          pagerank: round(coalesce(c.pagerank,0.0),3), seed: is_seed}}) AS scored
"""

_EXPAND_CYPHER = f"""
MATCH (s:Node) WHERE s.id IN $ids
OPTIONAL MATCH (s)-[r:{_REL_PATTERN}]-(m:Node)
WITH collect(DISTINCT s) AS seeds,
     collect(DISTINCT m) AS nbrs,
     collect(DISTINCT CASE WHEN r IS NOT NULL
             THEN {{a: startNode(r).id, t: type(r), b: endNode(r).id}} END) AS rels
WITH seeds + [x IN nbrs WHERE x IS NOT NULL] AS allNodes, rels
UNWIND allNodes AS n
WITH DISTINCT n, rels
RETURN collect({{id: n.id, kind: n.kind, name: n.name, content: n.content,
                 pagerank: round(coalesce(n.pagerank, 0.0), 4)}}) AS nodes,
       [x IN rels WHERE x IS NOT NULL] AS rels
"""


def kg_search(
    db: Neo4j,
    query: str,
    result_k: int | None = None,
    embed_fn: Optional[Callable[[str], list]] = None,
    expand: bool = True,
) -> KgResult:
    result_k = result_k or config.RESULT_K
    t_embed0 = time.time()
    qvec = embed_fn(query) if embed_fn is not None else embed.encode_one(query)
    t_embed = (time.time() - t_embed0) * 1000

    t_db0 = time.time()
    seed_rows = db.run(
        _SEED_CYPHER, qvec=qvec, ql=_lucene(query),
        kv=config.SEED_VECTOR_K * 3, kf=config.SEED_FULLTEXT_K * 3,
        seedN=config.SEED_VECTOR_K, resultk=result_k,
        wv=config.W_VECTOR, wp=config.W_PAGERANK, wseed=config.W_COMMUNITY,
    )
    scored = (seed_rows[0]["scored"] if seed_rows else []) or []
    seed_ids = [s["id"] for s in scored]
    score_by_id = {s["id"]: s for s in scored}

    nodes_data: dict[str, dict] = {}
    edges: list[dict] = []
    round_trips = 1
    if expand and seed_ids:
        exp = db.run(_EXPAND_CYPHER, ids=seed_ids)
        round_trips = 2
        if exp:
            for n in exp[0]["nodes"]:
                nodes_data[n["id"]] = n
            keep = set(nodes_data.keys())
            seen = set()
            for r in exp[0]["rels"]:
                key = (r["a"], r["t"], r["b"])
                if r["a"] in keep and r["b"] in keep and key not in seen:
                    seen.add(key)
                    edges.append(r)
    # Ensure all seeds are present even if expansion missed them.
    for sid in seed_ids:
        nodes_data.setdefault(sid, {**score_by_id[sid]})

    # Deliverable-intent boost: guarantee the production-side pages are in the
    # plan when the query names a deliverable (deck/infographic/scrolly/…).
    intent_scores: dict[str, float] = {}
    intent_ids = [tid for rx, tid in _INTENT_TOOLS if rx.search(query)]
    if expand and intent_ids:
        boost = db.run(_INTENT_CYPHER, tids=intent_ids)
        round_trips += 1
        for row in boost:
            nodes_data.setdefault(row["tid"], {
                "id": row["tid"], "kind": row["tkind"], "name": row["tname"],
                "content": row["tcontent"], "pagerank": row["tpr"]})
            intent_scores[row["tid"]] = 0.55  # outrank incidental tool hits
            seen_e = {(e["a"], e["t"], e["b"]) for e in edges}
            for nb in row["nbrs"]:
                nodes_data.setdefault(nb["id"], {
                    "id": nb["id"], "kind": nb["kind"], "name": nb["name"],
                    "content": nb["content"], "pagerank": nb["pagerank"]})
                # The whole spec neighbourhood is intent-routed — format_plan
                # must-ships it (else the Deck/recipe section the deliverable
                # ask exists for is the first thing the budget squeezes out).
                intent_scores.setdefault(nb["id"], 0.45)
                r = nb.get("rel")
                if r and (r["a"], r["t"], r["b"]) not in seen_e:
                    seen_e.add((r["a"], r["t"], r["b"]))
                    edges.append(r)
    t_db = (time.time() - t_db0) * 1000

    nodes = []
    for nid, n in nodes_data.items():
        s = score_by_id.get(nid)
        nodes.append(KgNode(
            id=nid, kind=n.get("kind", ""), name=n.get("name", ""),
            content=n.get("content", "") or "",
            pagerank=float(n.get("pagerank", 0.0) or 0.0),
            score=float(s["score"]) if s else intent_scores.get(nid, 0.0),
            signals=(s or {}).get("signals", {} if nid not in intent_scores
                                  else {"intent": 1.0}),
            is_seed=nid in score_by_id,
        ))
    # seeds first (by score), then plan-context neighbours (by pagerank)
    nodes.sort(key=lambda n: (n.is_seed, n.score, n.pagerank), reverse=True)
    return KgResult(query=query, nodes=nodes, edges=edges,
                    timings_ms={"embed": round(t_embed, 1), "db": round(t_db, 1),
                                "total": round(t_embed + t_db, 1)},
                    db_round_trips=round_trips)


def _trunc(text: str, cap: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= cap else text[:cap].rstrip() + " …"


def format_plan(res: KgResult, *, sql_cap: int = 2400, other_cap: int = 600,
                budget: int | None = None) -> str:
    """Render a KgResult as a PLAN the agent acts on (no file reads needed).

    Budgeted: per-section item caps (_SECTION_SPECS) + a global char budget so
    one find_skill call costs ~1-2k tokens, not 9k. Seeds outrank neighbours;
    within a section neighbours are ordered by pagerank.
    """
    budget = budget or PLAN_BUDGET
    if not res.nodes:
        return (f"find_skill: no graph match for {res.query!r}. Rephrase with the "
                "concrete task (metric + chart/deck/genie).")
    by_kind: dict[str, list[KgNode]] = defaultdict(list)
    for n in res.nodes:
        by_kind[n.kind].append(n)

    seeds = [n for n in res.nodes if n.is_seed][:3]
    lines = [
        f"# Plan for: {res.query!r}",
        "_traversed the skills knowledge graph — "
        f"{len(res.nodes)} nodes, {len(res.edges)} relations, "
        f"{res.db_round_trips} round-trips, {res.timings_ms.get('total','?')}ms_",
    ]
    if seeds:
        lines.append("**Best match:** " + " · ".join(f"{n.name} ({n.kind})" for n in seeds))
    lines.append("")

    # Seed adjacency: how strongly a neighbour hangs off the query's seeds.
    # Orders non-seed items within a section — a node tied to the top-scored
    # seeds beats a globally-central hub (pagerank is only the tie-break).
    seed_score = {n.id: n.score for n in res.nodes if n.is_seed}
    seed_adj: dict[str, float] = defaultdict(float)
    for e in res.edges:
        if e["a"] in seed_score:
            seed_adj[e["b"]] += seed_score[e["a"]]
        if e["b"] in seed_score:
            seed_adj[e["a"]] += seed_score[e["b"]]

    # Build capped, ranked item lists per section. Tie-break by content
    # completeness: a full pattern page (verbatim SQL) beats a short fragment
    # when both hang off the same seeds.
    section_items: list[tuple[str, list[KgNode]]] = []
    assigned: set[str] = set()
    for title, kinds, max_items in _SECTION_SPECS:
        items = []
        for k in kinds:
            items += by_kind.get(k, [])
        items = [n for n in items if n.id not in assigned]
        if not items:
            continue
        items.sort(key=lambda n: (n.is_seed, n.score, seed_adj.get(n.id, 0.0),
                                  min(len(n.content), 1500), n.pagerank),
                   reverse=True)
        items = items[:max_items]
        assigned.update(n.id for n in items)
        section_items.append((title, items))

    def _entry(n: KgNode, cap: int | None = None) -> list[str]:
        if cap is None:
            cap = sql_cap if n.kind == "SqlPattern" else other_cap
        body = _trunc(n.content, cap)
        e = [f"- **{n.name}**"]
        if body:
            e.append(body)
        return e

    # Two-pass budget over the FINAL string: SEEDS always ship (they are the
    # scored top-k — the whole point of the query); non-seed neighbours fill
    # what budget remains. This stops long neighbour SQL from crowding out a
    # top-seeded Finding whose section happens to come later in the order.
    # A reserve is held back for the Relationships footer + truncation note so
    # the rendered plan respects the budget (the footer used to be appended
    # un-counted, overshooting by ~1k chars). A seed that would still blow the
    # budget ships as headline + teaser — degraded, never dropped.
    reserve = 620 if res.edges else 100
    body_budget = max(budget - reserve, 1500)
    used = sum(len(l) + 1 for l in lines)
    chosen: dict[str, list[KgNode]] = {t: [] for t, _ in section_items}
    entry_caps: dict[str, int | None] = {}
    headers_counted: set[str] = set()
    teasered = False

    # Priority tiers: 0 = seeds (the scored top-k), 1 = must-ship context:
    # intent-routed spec pages (the Deck/recipe neighbourhood a deliverable
    # ask exists for) and GenieSpace pages (the "never guess a space ID"
    # contract — dropping one sends the agent on a space-id-hunting re-call),
    # 2 = ordinary expansion neighbours. Tiers 0-1 must ship — past the
    # budget they degrade to headline + teaser; tier 2 simply drops.
    def _tier(n: KgNode) -> int:
        if n.is_seed:
            return 0
        return 1 if (n.signals.get("intent") or n.kind == "GenieSpace") else 2

    for tier in (0, 1, 2):
        for title, items in section_items:
            for n in items:
                if _tier(n) != tier or n in chosen[title]:
                    continue
                cap: int | None = None
                cost = sum(len(l) + 1 for l in _entry(n))
                header_cost = 0 if title in headers_counted else len(title) + 5
                if used + cost + header_cost > body_budget:
                    if tier == 2:
                        continue
                    cap = 300
                    teasered = True
                    cost = sum(len(l) + 1 for l in _entry(n, cap))
                chosen[title].append(n)
                entry_caps[n.id] = cap
                headers_counted.add(title)
                used += cost + header_cost
    emitted: set[str] = set()
    truncated = teasered
    for title, items in section_items:
        picked = [n for n in items if n in chosen[title]]
        if len(picked) < len(items):
            truncated = True
        if not picked:
            continue
        lines.append(f"## {title}")
        for n in picked:
            emitted.add(n.id)
            lines += _entry(n, entry_caps.get(n.id))
        lines.append("")
    if truncated:
        lines.append("_…plan trimmed to budget — re-call find_skill with a "
                     "narrower query for more on a specific sub-topic._")
        lines.append("")

    # Show the key relationships AMONG EMITTED nodes so the agent sees WHY
    # these connect (cheap: names only).
    if res.edges:
        name_by_id = {n.id: n.name for n in res.nodes}
        rel_lines = []
        for e in res.edges:
            if e["a"] in emitted and e["b"] in emitted:
                a, b = name_by_id.get(e["a"], e["a"]), name_by_id.get(e["b"], e["b"])
                rel_lines.append(f"  {a} —{e['t']}→ {b}")
            if len(rel_lines) >= 8:
                break
        if rel_lines:
            lines.append("## Relationships")
            lines += rel_lines
    return "\n".join(lines).rstrip()


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "genie space and sql for the district access gap (zero-facility districts) and how to visualize it"
    with Neo4j() as db:
        res = kg_search(db, q)
    print(format_plan(res))
    print(f"\n[timings {res.timings_ms} · round-trips {res.db_round_trips} · payload {res.payload_chars()} chars]")

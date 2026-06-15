"""Load a graph seed (or any {nodes, edges} extractor output) into Neo4j.

Self-contained: reuses the orchestrator's own ``brain/`` (db + embeddings) so
the vectors and indexes (``kg_embeddings`` / ``kg_fulltext``, ``:Node`` + kind
label, ``embed_text``) are byte-for-byte what ``find_skill`` queries at runtime.
Mirrors ``neo4j/hackathon-brain/kg/merge_load.py`` but with no cross-repo import
and additive-by-default (so enriching the graph never wipes prior work).

    # structural dry run, no embeddings, no wipe:
    python -m prep.seed_load --seed prep/out/graph_seed.json --no-embed

    # full load (embeds via databricks-gte-large-en, builds indexes):
    python -m prep.seed_load --seed prep/out/graph_seed.json

    # clean rebuild (wipe first) + add the enriched skill/findings nodes too:
    python -m prep.seed_load --seed prep/out/graph_seed.json --wipe --also prep/out/skill_nodes.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from prep._common import load_config

_SLUG = re.compile(r"[^a-z0-9]+")
_EMBED_PROPS = ["definition", "formula", "statement", "rationale", "when_to_use",
                "claim", "evidence", "why", "question", "summary", "data_shape",
                "archetype", "space_id", "fq_name", "grain", "primary_key",
                "signature", "produces", "intent", "rule_id", "unit", "iso3"]
_RESERVED = {"id", "name", "content", "kind", "embedding", "pagerank",
             "community", "embed_text", "source", "sources"}


def canonical_id(node_type: str, name: str) -> str:
    slug = _SLUG.sub("_", (name or "").strip().lower()).strip("_")
    return f"{node_type}:{slug}" if slug else f"{node_type}:_"


def merge_nodes(raw_nodes: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n in raw_nodes:
        ntype, name = n.get("type"), (n.get("name") or "").strip()
        if not ntype or not name:
            continue
        nid = canonical_id(ntype, name)
        content = (n.get("content") or "").strip()
        props = {k: str(v) for k, v in (n.get("props") or {}).items()
                 if v not in (None, "") and k not in _RESERVED}
        if nid not in out:
            out[nid] = {"id": nid, "kind": ntype, "name": name,
                        "content": content, "props": dict(props)}
        else:
            cur = out[nid]
            if len(content) > len(cur["content"]):
                cur["content"] = content
            for k, v in props.items():
                cur["props"].setdefault(k, v)
    return out


def resolve_edges(raw_edges: list[dict], nodes: dict[str, dict]) -> tuple[list[dict], int]:
    seen, out, dropped = set(), [], 0
    for e in raw_edges:
        et = e.get("type")
        sid = canonical_id(e.get("from_type", ""), (e.get("from_name") or "").strip())
        tid = canonical_id(e.get("to_type", ""), (e.get("to_name") or "").strip())
        if not et or sid not in nodes or tid not in nodes or sid == tid:
            dropped += 1
            continue
        key = (sid, et, tid)
        if key in seen:
            continue
        seen.add(key)
        out.append({"from": sid, "type": et, "to": tid,
                    "props": {k: str(v) for k, v in (e.get("props") or {}).items() if v not in (None, "")}})
    return out, dropped


def embed_text(node: dict, cap: int = 2200) -> str:
    parts = [f"[{node['kind']}] {node['name']}"]
    for p in _EMBED_PROPS:
        v = node["props"].get(p)
        if v:
            parts.append(f"{p}: {v}")
    if node["content"]:
        parts.append(node["content"])
    return "\n".join(parts)[:cap]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load a graph seed into Neo4j (Aura).")
    ap.add_argument("--seed", required=True, help="graph_seed.json")
    ap.add_argument("--also", action="append", default=[], help="extra {nodes,edges} files to merge in")
    ap.add_argument("--config", help="workspace_config.yml")
    ap.add_argument("--wipe", action="store_true", help="DETACH DELETE the graph first (clean rebuild)")
    ap.add_argument("--no-embed", action="store_true", help="skip embeddings (structural dry run)")
    ap.add_argument("--no-analytics", action="store_true", help="skip networkx pagerank/louvain")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    # Match runtime embeddings: gte-large-en over HTTPS, no torch.
    os.environ.setdefault("BRAIN_EMBED_BACKEND", "databricks")
    os.environ.setdefault("BRAIN_EMBED_ENDPOINT", cfg["embed_endpoint"])
    if cfg["host"]:
        os.environ.setdefault("DATABRICKS_HOST", cfg["host"])
    if cfg["token"]:
        os.environ.setdefault("DATABRICKS_TOKEN", cfg["token"])

    raw_nodes: list[dict] = []
    raw_edges: list[dict] = []
    for fpath in [args.seed, *args.also]:
        d = json.loads(Path(fpath).read_text())
        raw_nodes += d.get("nodes", [])
        raw_edges += d.get("edges", [])

    nodes = merge_nodes(raw_nodes)
    edges, dropped = resolve_edges(raw_edges, nodes)
    by_kind: dict[str, int] = defaultdict(int)
    for n in nodes.values():
        by_kind[n["kind"]] += 1
    print(f"[load] merged → {len(nodes)} nodes, {len(edges)} edges ({dropped} dropped)")
    print(f"[load] by kind: {dict(sorted(by_kind.items()))}")
    for n in nodes.values():
        n["embed_text"] = embed_text(n)

    # Imports deferred until AFTER env is set so brain.config picks up the backend.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from brain.db import Neo4j  # noqa: E402

    if not (cfg["neo4j_uri"] and cfg["neo4j_password"]):
        print("[load] !! Neo4j creds missing — set neo4j.* in workspace_config.yml or NEO4J_* env.",
              file=sys.stderr)
        return 2

    with Neo4j(uri=cfg["neo4j_uri"], user=cfg["neo4j_user"],
               password=cfg["neo4j_password"], database=cfg["neo4j_database"]) as db:
        info = db.verify()
        print(f"[load] neo4j {info['neo4j']['version']} {info['neo4j']['edition']} · gds={info['gds']}")
        if args.wipe:
            print("[load] wiping graph…")
            db.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS")
        db.run("CREATE CONSTRAINT kg_node_id IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE")

        rows = [{"id": n["id"], "kind": n["kind"], "name": n["name"], "content": n["content"],
                 "embed_text": n["embed_text"],
                 "props": {k: v for k, v in n["props"].items() if k not in _RESERVED}}
                for n in nodes.values()]
        db.run(
            "UNWIND $rows AS r MERGE (n:Node {id:r.id}) "
            "SET n.kind=r.kind, n.name=r.name, n.content=r.content, "
            "    n.embed_text=r.embed_text, n += r.props "
            "WITH n, r CALL apoc.create.addLabels(n, [r.kind]) YIELD node RETURN count(node)",
            rows=rows)
        print(f"[load] upserted {len(rows)} nodes")

        erows = [{"from": e["from"], "to": e["to"], "type": e["type"], "props": e["props"]} for e in edges]
        if erows:
            db.run(
                "UNWIND $rows AS r MATCH (a:Node {id:r.from}),(b:Node {id:r.to}) "
                "CALL apoc.merge.relationship(a, r.type, {}, r.props, b, {}) YIELD rel RETURN count(rel)",
                rows=erows)
        print(f"[load] upserted {len(erows)} edges")

        db.run("CREATE FULLTEXT INDEX kg_fulltext IF NOT EXISTS "
               "FOR (n:Node) ON EACH [n.name, n.content, n.embed_text]")

        if not args.no_embed:
            from brain import embed as bembed  # noqa: E402
            ids = list(nodes.keys())
            texts = [nodes[i]["embed_text"] for i in ids]
            print(f"[load] embedding {len(texts)} nodes via {os.environ['BRAIN_EMBED_ENDPOINT']}…")
            t0 = time.time()
            vecs = bembed.encode(texts)
            dim = int(vecs.shape[1])
            print(f"[load]   embedded in {time.time()-t0:.0f}s, dim={dim}")
            db.run(
                "CREATE VECTOR INDEX kg_embeddings IF NOT EXISTS FOR (n:Node) ON (n.embedding) "
                "OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}}",
                dim=dim)
            db.run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.embedding=r.v",
                   rows=[{"id": ids[i], "v": vecs[i].tolist()} for i in range(len(ids))])
            print("[load]   vector index built + embeddings set")

            if not args.no_analytics and edges:
                _analytics(db, list(nodes.keys()), edges)

        counts = db.run_one("MATCH (n:Node) WITH count(n) AS nodes "
                            "MATCH ()-[r]->() RETURN nodes, count(r) AS rels")
        print(f"[load] DONE — graph now has {counts['nodes']} nodes, {counts['rels']} relationships")
    print("[load] verify: python -m brain.kg_retrieve \"a question about the data\"")
    return 0


def _analytics(db, ids: list[str], edges: list[dict]) -> None:
    try:
        import networkx as nx
    except ImportError:
        print("[load]   (networkx absent — skipping pagerank/louvain)")
        return
    G = nx.DiGraph()
    G.add_nodes_from(ids)
    for e in edges:
        G.add_edge(e["from"], e["to"])
    if not G.number_of_edges():
        return
    pr = nx.pagerank(G)
    mx = max(pr.values()) or 1.0
    db.run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.pagerank=r.pr",
           rows=[{"id": k, "pr": round(v / mx, 6)} for k, v in pr.items()])
    comms = nx.community.louvain_communities(G.to_undirected(), seed=42)
    db.run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.community=r.c",
           rows=[{"id": m, "c": ci} for ci, members in enumerate(comms) for m in members])
    print(f"[load]   analytics: pagerank({len(pr)}) + {len(comms)} communities")


if __name__ == "__main__":
    sys.exit(main())

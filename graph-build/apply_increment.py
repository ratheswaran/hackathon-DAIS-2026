"""Incremental apply (no wipe): upsert the R-facility-dedup rule + the updated
facilities_total metric (embed just those), then add kNN SIMILAR_TO edges for the
explorer and recompute pagerank/louvain over TYPED edges only.
"""
import os, sys, configparser
import numpy as np
from pathlib import Path
REPO_ROOT = Path(os.environ.get("HACKATHON_REPO_ROOT", Path(__file__).resolve().parent.parent))
ORCH = REPO_ROOT / "hackathon-orchestrator-neo4j"
GB = Path(__file__).resolve().parent  # this graph-build dir holds the seed JSONs
PROFILE = os.environ.get("DATABRICKS_PROFILE", "hackathon")

# Neo4j creds: env vars win; else read a gitignored KEY=VALUE creds file (NEO4J_CREDS_FILE).
NU = os.environ.get("NEO4J_URI"); NUSER = os.environ.get("NEO4J_USERNAME", "neo4j")
NPW = os.environ.get("NEO4J_PASSWORD"); NDB = os.environ.get("NEO4J_DATABASE", "neo4j")
if not (NU and NPW):
    _creds = os.environ.get("NEO4J_CREDS_FILE")
    if not _creds:
        sys.exit("Set NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD/NEO4J_DATABASE, "
                 "or NEO4J_CREDS_FILE=<path to a gitignored KEY=VALUE creds file>.")
    for line in Path(_creds).read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k == "NEO4J_URI": NU = v
            elif k == "NEO4J_USERNAME": NUSER = v
            elif k == "NEO4J_PASSWORD": NPW = v
            elif k == "NEO4J_DATABASE": NDB = v
cfg = configparser.ConfigParser(); cfg.read(os.path.expanduser("~/.databrickscfg"))
host = cfg[PROFILE]["host"].rstrip("/")
if not host.startswith("http"): host = "https://" + host
os.environ.update(DATABRICKS_HOST=host, DATABRICKS_TOKEN=cfg[PROFILE]["token"],
                  BRAIN_EMBED_BACKEND="databricks", BRAIN_EMBED_ENDPOINT="databricks-gte-large-en",
                  BRAIN_EMBED_BATCH="1", BRAIN_EMBED_PAUSE="0.5")
sys.path.insert(0, str(ORCH))
import json
from neo4j import GraphDatabase
from prep.seed_load import merge_nodes, embed_text, canonical_id, _RESERVED
from brain import embed as bembed

seed = json.loads((GB / "domain_seed.json").read_text())
nodes = merge_nodes(seed["nodes"])
for n in nodes.values(): n["embed_text"] = embed_text(n)

targets = ["Rule:r_facility_dedup", "Metric:facilities_total"]
drv = GraphDatabase.driver(NU, auth=(NUSER, NPW))
def run(q, **p):
    with drv.session(database=NDB) as s: return [r.data() for r in s.run(q, **p)]

# 1. upsert the 2 target nodes + embed them
rows = [{"id": t, "kind": nodes[t]["kind"], "name": nodes[t]["name"], "content": nodes[t]["content"],
         "embed_text": nodes[t]["embed_text"],
         "props": {k: v for k, v in nodes[t]["props"].items() if k not in _RESERVED}} for t in targets]
run("UNWIND $rows AS r MERGE (n:Node {id:r.id}) SET n.kind=r.kind, n.name=r.name, n.content=r.content, "
    "n.embed_text=r.embed_text, n += r.props WITH n, r CALL apoc.create.addLabels(n,[r.kind]) YIELD node RETURN count(node)", rows=rows)
vecs = bembed.encode([nodes[t]["embed_text"] for t in targets])
run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.embedding=r.v",
    rows=[{"id": targets[i], "v": vecs[i].tolist()} for i in range(len(targets))])
print(f"[inc] upserted+embedded {len(targets)} target nodes")

# 2. upsert edges touching the targets
tset = set(targets)
erows = []
for e in seed["edges"]:
    sid = canonical_id(e["from_type"], e["from_name"]); tid = canonical_id(e["to_type"], e["to_name"])
    if sid in tset or tid in tset:
        erows.append({"from": sid, "to": tid, "type": e["type"]})
run("UNWIND $rows AS r MATCH (a:Node {id:r.from}),(b:Node {id:r.to}) "
    "CALL apoc.merge.relationship(a, r.type, {}, {}, b, {}) YIELD rel RETURN count(rel)", rows=erows)
print(f"[inc] upserted {len(erows)} edges touching targets")

# 3. kNN SIMILAR_TO for the explorer (drop old first), top-6, cutoff 0.55
run("MATCH ()-[r:SIMILAR_TO]->() DELETE r")
alln = run("MATCH (n:Node) WHERE n.embedding IS NOT NULL RETURN n.id AS id, n.embedding AS e ORDER BY n.id")
ids = [r["id"] for r in alln]; X = np.array([r["e"] for r in alln], dtype=np.float32)
X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
S = X @ X.T; np.fill_diagonal(S, -1.0)
K, CUT = 6, 0.55
sim_rows = []
for i in range(len(ids)):
    top = np.argsort(-S[i])[:K]
    for j in top:
        if S[i, j] >= CUT:
            sim_rows.append({"a": ids[i], "b": ids[j], "s": round(float(S[i, j]), 4)})
for k in range(0, len(sim_rows), 1000):
    run("UNWIND $rows AS r MATCH (a:Node {id:r.a}),(b:Node {id:r.b}) "
        "MERGE (a)-[x:SIMILAR_TO]->(b) SET x.score=r.s", rows=sim_rows[k:k+1000])
print(f"[inc] wrote {len(sim_rows)} SIMILAR_TO edges (top-{K}, cutoff {CUT})")

# 4. recompute pagerank/louvain on TYPED edges only (exclude SIMILAR_TO)
import networkx as nx
typed = run("MATCH (a:Node)-[r]->(b:Node) WHERE type(r)<>'SIMILAR_TO' RETURN a.id AS a, b.id AS b")
G = nx.DiGraph(); G.add_nodes_from(ids)
for e in typed: G.add_edge(e["a"], e["b"])
pr = nx.pagerank(G); mx = max(pr.values()) or 1.0
run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.pagerank=r.pr",
    rows=[{"id": k, "pr": round(v/mx, 6)} for k, v in pr.items()])
comms = nx.community.louvain_communities(G.to_undirected(), seed=42)
run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.community=r.c",
    rows=[{"id": m, "c": ci} for ci, members in enumerate(comms) for m in members])
print(f"[inc] recomputed pagerank({len(pr)}) + {len(comms)} communities on typed edges")

tot = run("MATCH (n:Node) RETURN count(n) AS c")[0]["c"]
rels = run("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
sim = run("MATCH ()-[r:SIMILAR_TO]->() RETURN count(r) AS c")[0]["c"]
print(f"[inc] DONE — {tot} nodes, {rels} rels ({sim} SIMILAR_TO + {rels-sim} typed)")
drv.close()

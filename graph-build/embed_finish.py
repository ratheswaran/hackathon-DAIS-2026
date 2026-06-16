"""Finish the rebuild: embed the already-loaded nodes (batch=1 for Free-Edition
gte-large-en), build the vector index, and compute pagerank/louvain.

Decoupled from the load so a rate-limit retry never re-wipes the graph. Reads
embed_text straight from the loaded :Node nodes.
"""
import os, sys, time, configparser
from pathlib import Path

REPO_ROOT = Path(os.environ.get("HACKATHON_REPO_ROOT", Path(__file__).resolve().parent.parent))
ORCH = REPO_ROOT / "hackathon-orchestrator-neo4j"
PROFILE = os.environ.get("DATABRICKS_PROFILE", "hackathon")

# Neo4j creds: env vars win; else read a gitignored KEY=VALUE creds file (NEO4J_CREDS_FILE).
NEO_URI = os.environ.get("NEO4J_URI"); NEO_USER = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO_PW = os.environ.get("NEO4J_PASSWORD"); NEO_DB = os.environ.get("NEO4J_DATABASE", "neo4j")
if not (NEO_URI and NEO_PW):
    _creds = os.environ.get("NEO4J_CREDS_FILE")
    if not _creds:
        sys.exit("Set NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD/NEO4J_DATABASE, "
                 "or NEO4J_CREDS_FILE=<path to a gitignored KEY=VALUE creds file>.")
    for line in Path(_creds).read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k == "NEO4J_URI": NEO_URI = v
            elif k == "NEO4J_USERNAME": NEO_USER = v
            elif k == "NEO4J_PASSWORD": NEO_PW = v
            elif k == "NEO4J_DATABASE": NEO_DB = v

cfg = configparser.ConfigParser(); cfg.read(os.path.expanduser("~/.databrickscfg"))
host = cfg[PROFILE]["host"].rstrip("/")
if not host.startswith("http"): host = "https://" + host
os.environ["DATABRICKS_HOST"] = host
os.environ["DATABRICKS_TOKEN"] = cfg[PROFILE]["token"]
os.environ["BRAIN_EMBED_BACKEND"] = "databricks"
os.environ["BRAIN_EMBED_ENDPOINT"] = "databricks-gte-large-en"
os.environ["BRAIN_EMBED_BATCH"] = "1"      # Free-Edition gte-large-en limits inputs-per-request
os.environ["BRAIN_EMBED_PAUSE"] = "0.5"

sys.path.insert(0, str(ORCH))
from neo4j import GraphDatabase
from brain import embed as bembed

drv = GraphDatabase.driver(NEO_URI, auth=(NEO_USER, NEO_PW))
def run(q, **p):
    with drv.session(database=NEO_DB) as s:
        return [r.data() for r in s.run(q, **p)]

rows = run("MATCH (n:Node) RETURN n.id AS id, n.embed_text AS t ORDER BY n.id")
ids = [r["id"] for r in rows]
texts = [r["t"] or r["id"] for r in rows]
already = run("MATCH (n:Node) WHERE n.embedding IS NOT NULL RETURN count(*) AS c")[0]["c"]
print(f"[embed] {len(ids)} nodes to embed (currently {already} embedded) — batch=1")

t0 = time.time()
vecs = bembed.encode(texts)           # batch=1 internally, retry/backoff on 429
dim = int(vecs.shape[1])
print(f"[embed] done in {time.time()-t0:.0f}s, dim={dim}")

run("CREATE VECTOR INDEX kg_embeddings IF NOT EXISTS FOR (n:Node) ON (n.embedding) "
    "OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}}", dim=dim)
# set embeddings in chunks
B = 200
for i in range(0, len(ids), B):
    payload = [{"id": ids[j], "v": vecs[j].tolist()} for j in range(i, min(i+B, len(ids)))]
    run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.embedding=r.v", rows=payload)
print("[embed] vector index built + embeddings set")

# pagerank + louvain (networkx) over the loaded typed edges
import networkx as nx
edges = run("MATCH (a:Node)-[r]->(b:Node) RETURN a.id AS a, b.id AS b")
G = nx.DiGraph(); G.add_nodes_from(ids)
for e in edges: G.add_edge(e["a"], e["b"])
pr = nx.pagerank(G); mx = max(pr.values()) or 1.0
run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.pagerank=r.pr",
    rows=[{"id": k, "pr": round(v/mx, 6)} for k, v in pr.items()])
comms = nx.community.louvain_communities(G.to_undirected(), seed=42)
run("UNWIND $rows AS r MATCH (n:Node {id:r.id}) SET n.community=r.c",
    rows=[{"id": m, "c": ci} for ci, members in enumerate(comms) for m in members])
print(f"[embed] analytics: pagerank({len(pr)}) + {len(comms)} communities")

c = run("MATCH (n:Node) WHERE n.embedding IS NOT NULL RETURN count(*) AS c")[0]["c"]
print(f"[embed] DONE — {c}/{len(ids)} nodes embedded")
drv.close()

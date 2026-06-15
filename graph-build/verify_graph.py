"""Acceptance test for the rebuilt graph: run find_skill (kg_retrieve) on
representative Medical-Desert queries + an ontology audit. Read-only."""
import os, sys, configparser
from pathlib import Path
BASE = Path("/Users/rathes/Library/CloudStorage/OneDrive-ResonanceAnalyticsEnterprise/Documents/MSc Business Analytics/05. Analytics in Business/Building A Open Harness Agent/databricks notebook")
ORCH = BASE / "hackathon-orchestrator-neo4j"
CREDS = BASE / "neo4j" / "Neo4j-2a3edbfb-Created-2026-06-09.txt"
for line in CREDS.read_text().splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if k == "NEO4J_URI": os.environ["NEO4J_URI"] = v
        elif k == "NEO4J_USERNAME": os.environ["NEO4J_USER"] = v
        elif k == "NEO4J_PASSWORD": os.environ["NEO4J_PASSWORD"] = v
        elif k == "NEO4J_DATABASE": os.environ["NEO4J_DATABASE"] = v
cfg = configparser.ConfigParser(); cfg.read(os.path.expanduser("~/.databrickscfg"))
host = cfg["hackathon"]["host"].rstrip("/")
if not host.startswith("http"): host = "https://" + host
os.environ["DATABRICKS_HOST"] = host
os.environ["DATABRICKS_TOKEN"] = cfg["hackathon"]["token"]
os.environ["BRAIN_EMBED_BACKEND"] = "databricks"
os.environ["BRAIN_EMBED_ENDPOINT"] = "databricks-gte-large-en"
os.environ["BRAIN_EMBED_BATCH"] = "1"
sys.path.insert(0, str(ORCH))
from brain.db import Neo4j
from brain import kg_retrieve

PROBES = [
    "where are India's medical deserts — high need and low facility coverage?",
    "does facility supply follow health need across districts?",
    "which districts have the worst child anaemia and stunting?",
    "can I trust this facility's claimed equipment and specialties?",
    "build a data story / infographic on India's medical deserts",
    "how do I join facilities to NFHS districts via PIN code?",
    "which states have the highest health burden?",
    "what must be fixed before I can trust this data?",
]
with Neo4j() as db:
    print("="*72, "\nONTOLOGY AUDIT\n", "="*72)
    for r in db.run("MATCH (n:Node) RETURN n.kind AS k, count(*) AS c ORDER BY c DESC"):
        print(f"  {r['k']:<14} {r['c']}")
    tot = db.run_one("MATCH (n:Node) RETURN count(n) AS c")["c"]
    rels = db.run_one("MATCH ()-[r]->() RETURN count(r) AS c")["c"]
    emb = db.run_one("MATCH (n:Node) WHERE n.embedding IS NOT NULL RETURN count(*) AS c")["c"]
    noemb = db.run("MATCH (n:Node) WHERE n.embedding IS NULL RETURN n.kind AS k, n.name AS n LIMIT 5")
    print(f"\n  total nodes={tot} rels={rels} embedded={emb}  (missing: {[ (x['k'],x['n']) for x in noemb]})")
    for ix in db.run("SHOW INDEXES YIELD name,type,state RETURN name,type,state"):
        print(f"  index {ix['name']:<16} {ix['type']:<10} {ix.get('state')}")

    print("\n" + "="*72, "\nFIND_SKILL PROBES\n", "="*72)
    for q in PROBES:
        res = kg_retrieve.kg_search(db, q)
        plan = kg_retrieve.format_plan(res)
        seeds = " · ".join(f"{n.name}({n.kind})" for n in res.nodes if n.is_seed)[:200]
        print(f"\n{'#'*68}\nQ: {q}\n  seeds: {seeds}\n  {len(res.nodes)} nodes/{len(res.edges)} rels · {res.timings_ms.get('total')}ms · {len(plan)} chars")
        # print first ~900 chars of the plan to eyeball relevance
        print("  --- plan ---")
        for ln in plan.splitlines()[:24]:
            print("  " + ln)

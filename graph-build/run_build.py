"""Rebuild the find_skill graph brain on Aura: WIPE + load the India-healthcare
domain seed + the kept skill/capability layer, embed via the event workspace's
gte-large-en (1024-dim), build indexes + pagerank/louvain.

Secrets are read at runtime from local files (never on the command line):
  - Neo4j (Aura) creds  : neo4j/Neo4j-2a3edbfb-Created-2026-06-09.txt
  - Databricks embed tok : ~/.databrickscfg [hackathon] (event workspace)

Usage:  python run_build.py            # full wipe+load+embed
        python run_build.py --no-embed # structural dry run (still wipes!)
"""
import os, sys, configparser
from pathlib import Path

BASE = Path("/Users/rathes/Library/CloudStorage/OneDrive-ResonanceAnalyticsEnterprise/Documents/MSc Business Analytics/05. Analytics in Business/Building A Open Harness Agent/databricks notebook")
ORCH = BASE / "hackathon-orchestrator-neo4j"
GB = BASE / "hackathon-session-2026-06-15" / "graph_build"
CREDS = BASE / "neo4j" / "Neo4j-2a3edbfb-Created-2026-06-09.txt"
PROFILE = "hackathon"  # event workspace — gte-large-en lives here

# --- Neo4j creds -> env ---
for line in CREDS.read_text().splitlines():
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if k == "NEO4J_URI": os.environ["NEO4J_URI"] = v
        elif k == "NEO4J_USERNAME": os.environ["NEO4J_USER"] = v
        elif k == "NEO4J_PASSWORD": os.environ["NEO4J_PASSWORD"] = v
        elif k == "NEO4J_DATABASE": os.environ["NEO4J_DATABASE"] = v

# --- Databricks embed creds -> env (event workspace) ---
cfg = configparser.ConfigParser(); cfg.read(os.path.expanduser("~/.databrickscfg"))
host = cfg[PROFILE]["host"].rstrip("/")
if not host.startswith("http"): host = "https://" + host
os.environ["DATABRICKS_HOST"] = host
os.environ["DATABRICKS_TOKEN"] = cfg[PROFILE]["token"]
os.environ["BRAIN_EMBED_BACKEND"] = "databricks"
os.environ["BRAIN_EMBED_ENDPOINT"] = "databricks-gte-large-en"
os.environ["BRAIN_EMBED_DIM"] = "1024"

print(f"[build] Neo4j {os.environ['NEO4J_URI']} db={os.environ['NEO4J_DATABASE']}")
print(f"[build] embed via {host} :: databricks-gte-large-en")

sys.path.insert(0, str(ORCH))
os.chdir(ORCH)
from prep import seed_load

argv = ["--seed", str(GB / "domain_seed.json"),
        "--also", str(GB / "skill_nodes.json"),
        "--wipe"]
if "--no-embed" in sys.argv:
    argv.append("--no-embed")
sys.exit(seed_load.main(argv))

"""Rebuild the find_skill graph brain on Aura: WIPE + load the India-healthcare
domain seed + the kept skill/capability layer, embed via the event workspace's
gte-large-en (1024-dim), build indexes + pagerank/louvain.

Secrets are read at runtime from the environment (never on the command line):
  - Neo4j (Aura) creds  : NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD / NEO4J_DATABASE
                          (or point NEO4J_CREDS_FILE at a gitignored KEY=VALUE creds file)
  - Databricks embed tok : ~/.databrickscfg [<DATABRICKS_PROFILE or "hackathon">]

Usage:  python run_build.py            # full wipe+load+embed
        python run_build.py --no-embed # structural dry run (still wipes!)
"""
import os, sys, configparser
from pathlib import Path

# Repo-relative by default; override the repo root via HACKATHON_REPO_ROOT.
REPO_ROOT = Path(os.environ.get("HACKATHON_REPO_ROOT", Path(__file__).resolve().parent.parent))
ORCH = REPO_ROOT / "hackathon-orchestrator-neo4j"
GB = Path(__file__).resolve().parent  # this graph-build dir holds the seed JSONs
PROFILE = os.environ.get("DATABRICKS_PROFILE", "hackathon")  # workspace where gte-large-en lives

# --- Neo4j creds -> env (env vars win; else read a gitignored KEY=VALUE creds file) ---
def _load_neo4j_creds():
    if os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD"):
        os.environ.setdefault("NEO4J_USER", os.environ.get("NEO4J_USERNAME", "neo4j"))
        os.environ.setdefault("NEO4J_DATABASE", os.environ.get("NEO4J_DATABASE", "neo4j"))
        return
    creds_file = os.environ.get("NEO4J_CREDS_FILE")
    if not creds_file:
        sys.exit("Set NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD/NEO4J_DATABASE, "
                 "or NEO4J_CREDS_FILE=<path to a gitignored KEY=VALUE creds file>.")
    for line in Path(creds_file).read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            if k == "NEO4J_URI": os.environ["NEO4J_URI"] = v
            elif k == "NEO4J_USERNAME": os.environ["NEO4J_USER"] = v
            elif k == "NEO4J_PASSWORD": os.environ["NEO4J_PASSWORD"] = v
            elif k == "NEO4J_DATABASE": os.environ["NEO4J_DATABASE"] = v

_load_neo4j_creds()

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

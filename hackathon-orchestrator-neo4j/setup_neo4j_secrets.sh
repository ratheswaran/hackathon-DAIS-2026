#!/usr/bin/env bash
# Put the Neo4j (Aura) connection into a Databricks secret scope so the serving
# endpoint resolves NEO4J_* at runtime via {{secrets/<scope>/neo4j-*}} env refs.
# This mirrors the SAP GraphRAG reference (00_init.py creates neo4j-host/-key).
#
# Run ONCE per workspace before deploying with `neo4j.inject_plaintext: false`.
# With inject_plaintext: true (the dry-run default) the deploy bakes the creds
# into the endpoint env vars instead and you don't need this — but the secret
# scope is the production-correct path.
#
# Usage:
#   ./setup_neo4j_secrets.sh                      # reads creds from workspace_config.yml
#   PROFILE=hackathon-test ./setup_neo4j_secrets.sh
#   NEO4J_URI=... NEO4J_USER=... NEO4J_PASSWORD=... NEO4J_DATABASE=... ./setup_neo4j_secrets.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${PROFILE:-hackathon}"
SCOPE="${SCOPE:-agent-secrets}"
CFG="$SCRIPT_DIR/workspace_config.yml"

# Pull creds from workspace_config.yml unless overridden by env.
yval() { grep -E "^[[:space:]]*$1:" "$CFG" | head -1 | sed -E 's/^[^:]*:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/'; }
NEO4J_URI="${NEO4J_URI:-$(yval uri)}"
NEO4J_USER="${NEO4J_USER:-$(yval user)}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-$(yval password)}"
NEO4J_DATABASE="${NEO4J_DATABASE:-$(yval database)}"

[ -n "$NEO4J_URI" ] && [ -n "$NEO4J_PASSWORD" ] || { echo "ERROR: NEO4J_URI/PASSWORD not found (set env or workspace_config.yml neo4j:)"; exit 1; }

echo "Profile=$PROFILE  Scope=$SCOPE"
echo "  NEO4J_URI=$NEO4J_URI  NEO4J_USER=$NEO4J_USER  NEO4J_DATABASE=$NEO4J_DATABASE"

# Create the scope (ignore 'already exists').
databricks secrets create-scope "$SCOPE" --profile "$PROFILE" 2>/dev/null \
  || echo "  scope '$SCOPE' already exists (ok)"

put() {
  echo "  put $SCOPE/$1"
  databricks secrets put-secret "$SCOPE" "$1" --string-value "$2" --profile "$PROFILE"
}
put neo4j-uri      "$NEO4J_URI"
put neo4j-user     "$NEO4J_USER"
put neo4j-password "$NEO4J_PASSWORD"
put neo4j-database "$NEO4J_DATABASE"

echo "Done. Secrets in scope '$SCOPE': $(databricks secrets list-secrets "$SCOPE" --profile "$PROFILE" --output json | python3 -c 'import sys,json;print(", ".join(s["key"] for s in json.load(sys.stdin)))' 2>/dev/null)"
echo "Now set neo4j.inject_plaintext: false in workspace_config.yml and redeploy."

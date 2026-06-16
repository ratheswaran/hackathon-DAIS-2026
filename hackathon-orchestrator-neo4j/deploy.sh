#!/usr/bin/env bash
# hackathon-orchestrator deploy ritual
#
# One command: stage local sources to /tmp, push to workspace, submit serverless
# job, poll until terminal, dump task output on failure.
#
# Usage:
#   ./deploy.sh                  # full deploy + poll + dump errors
#   ./deploy.sh --no-poll        # submit + exit, print run_id
#   ./deploy.sh --logs <run_id>  # re-fetch logs for an existing run
#   ./deploy.sh --push-only      # rsync + workspace import-dir, skip job submit
#   ./deploy.sh --status         # show endpoint + model version state
#   ./deploy.sh -h | --help
#
# Env overrides (defaults match the Free Edition hackathon workspace):
#   PROFILE         (default: hackathon-test) — Databricks CLI profile
#   WORKSPACE_PATH  (default: /Workspace/Users/your-email@example.com/hackathon/orchestrator)
#   ENDPOINT_NAME   (default: agents_workspace-hackathon-orchestrator_agent_v3)
#   MODEL_NAME      (default: workspace.hackathon.orchestrator_agent_v3)
#   POLL_TIMEOUT    (default: 1500 seconds)
#   POLL_INTERVAL   (default: 60 seconds)
#
set -euo pipefail

# --- defaults --------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="${PROFILE:-hackathon}"
WORKSPACE_PATH="${WORKSPACE_PATH:-/Workspace/Users/your-email@example.com/hackathon/orchestrator-neo4j}"
ENDPOINT_NAME="${ENDPOINT_NAME:-agents_workspace-hackathon-orchestrator_agent_neo4j}"
MODEL_NAME="${MODEL_NAME:-workspace.hackathon.orchestrator_agent_neo4j}"
POLL_TIMEOUT="${POLL_TIMEOUT:-1500}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"
STAGE_DIR="/tmp/hackathon-orchestrator-neo4j-stage"
JOB_SPEC="$SCRIPT_DIR/deployment/job-spec.json"

# --- helpers ---------------------------------------------------------------
log()  { echo "[$(date +%H:%M:%S)] $*" >&2; }
die()  { log "ERROR: $*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"; }

usage() { sed -n '2,30p' "$0"; exit 0; }

stage() {
  log "Staging local sources → $STAGE_DIR"
  rm -rf "$STAGE_DIR"
  mkdir -p "$STAGE_DIR"
  # -aL resolves symlinks (the `skills` symlink → ../hackathon-skills)
  rsync -aL \
    --exclude '__pycache__' --exclude '*.pyc' \
    --exclude '.pytest_cache' --exclude 'tests*' --exclude 'evals' --exclude 'lab' \
    --exclude '.venv*' --exclude '.DS_Store' \
    --exclude 'deploy.sh' --exclude 'DEPLOY.md' \
    "$SCRIPT_DIR/" "$STAGE_DIR/"
  log "Staged $(du -sh "$STAGE_DIR" | cut -f1) of sources"
}

push() {
  log "Pushing → $WORKSPACE_PATH (profile=$PROFILE)"
  databricks workspace import-dir "$STAGE_DIR" "$WORKSPACE_PATH" \
    --overwrite --profile "$PROFILE" >/dev/null
  log "Push complete"
}

submit() {
  log "Submitting job (no-wait)…"
  local run_id
  run_id=$(databricks jobs submit --no-wait \
    --json "@$JOB_SPEC" --profile "$PROFILE" \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['run_id'])")
  log "run_id = $run_id"
  echo "$run_id"
}

poll() {
  local run_id="$1"
  local deadline=$(( $(date +%s) + POLL_TIMEOUT ))
  log "Polling run $run_id (timeout ${POLL_TIMEOUT}s, every ${POLL_INTERVAL}s)…"
  while [ "$(date +%s)" -lt "$deadline" ]; do
    local state
    state=$(databricks jobs get-run "$run_id" --profile "$PROFILE" 2>/dev/null \
      | python3 -c "import sys, json; d=json.load(sys.stdin); s=d.get('state',{}); print(s.get('life_cycle_state',''), s.get('result_state','') or '-')")
    log "state: $state"
    local lc="${state%% *}"
    case "$lc" in
      TERMINATED|INTERNAL_ERROR|SKIPPED) return 0 ;;
    esac
    sleep "$POLL_INTERVAL"
  done
  die "poll timeout — run $run_id still active after ${POLL_TIMEOUT}s"
}

dump_output() {
  local run_id="$1"
  echo
  echo "=========================================================="
  echo "  Run summary: $run_id"
  echo "=========================================================="
  databricks jobs get-run "$run_id" --profile "$PROFILE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d.get('state', {})
print(f\"  result      : {s.get('result_state')}\")
print(f\"  state msg   : {(s.get('state_message') or '')[:400]}\")
print(f\"  run_page    : {d.get('run_page_url')}\")
"
  databricks jobs get-run "$run_id" --profile "$PROFILE" \
    | python3 -c "import sys, json; [print(t.get('run_id')) for t in json.load(sys.stdin).get('tasks', [])]" \
    | while read -r tid; do
        [ -z "$tid" ] && continue
        echo
        echo "  --- task run $tid ---"
        databricks jobs get-run-output "$tid" --profile "$PROFILE" 2>&1 \
          | python3 -c "
import sys, json, re
try: d = json.load(sys.stdin)
except: sys.exit(0)
err = (d.get('error') or '').strip()
trace = re.sub(r'\x1b\[[0-9;]*m', '', d.get('error_trace') or '')
nb = (d.get('notebook_output') or {}).get('result') or ''
if err:   print(f'  error      : {err[:600]}')
if trace: print(f'  trace tail : ...{trace[-1200:]}')
if nb:    print(f'  nb output  : {nb[:400]}')
"
      done
}

show_status() {
  echo "=== Serving endpoint ==="
  databricks serving-endpoints get "$ENDPOINT_NAME" --profile "$PROFILE" 2>&1 \
    | python3 -c "
import sys, json
try: d = json.load(sys.stdin)
except: print(sys.stdin.read()); sys.exit(0)
print(f\"  name        : {d.get('name')}\")
s = d.get('state') or {}
print(f\"  ready       : {s.get('ready')}\")
print(f\"  config_update: {s.get('config_update')}\")
served = (d.get('config') or {}).get('served_entities') or []
for se in served:
    print(f\"  entity      : {se.get('entity_name')} v{se.get('entity_version')} \"
          f\"size={se.get('workload_size')} s2z={se.get('scale_to_zero_enabled')}\")
"
  echo
  echo "=== UC model versions ==="
  databricks api get "/api/2.1/unity-catalog/models/${MODEL_NAME}/versions" \
    --profile "$PROFILE" 2>&1 | python3 -c "
import sys, json
try: d = json.load(sys.stdin)
except: print(sys.stdin.read()); sys.exit(0)
for v in (d.get('model_versions') or [])[-5:]:
    print(f\"  v{v.get('version')} | status={v.get('status')} | run_id={v.get('run_id')}\")
" 2>/dev/null || echo "  (model versions list unavailable)"
}

# --- main ------------------------------------------------------------------
need databricks
need rsync
need python3

cmd="${1:-deploy}"

case "$cmd" in
  -h|--help) usage ;;

  --status)
    show_status
    ;;

  --logs)
    [ $# -ge 2 ] || die "--logs requires <run_id>"
    dump_output "$2"
    ;;

  --push-only)
    stage; push
    log "Push complete. Skipping job submit."
    ;;

  --no-poll)
    stage; push
    RUN_ID=$(submit)
    log "Job submitted. Not polling. Use './deploy.sh --logs $RUN_ID' to fetch output later."
    echo "$RUN_ID"
    ;;

  deploy|"")
    stage; push
    RUN_ID=$(submit)
    poll "$RUN_ID" || true
    dump_output "$RUN_ID"
    ;;

  *)
    die "unknown command: $cmd (try --help)"
    ;;
esac

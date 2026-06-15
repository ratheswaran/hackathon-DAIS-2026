# hackathon-orchestrator — deploy runbook

One-command deploy of the hackathon orchestrator agent to Databricks Free Edition. Use this during the Project Period (Jun 15-16 2026) to ship changes fast.

## TL;DR

```bash
./deploy.sh        # full deploy + poll + show errors on failure
./smoke_test.sh    # send a Sudan query and print the response
```

If the endpoint is READY after `./deploy.sh` and `./smoke_test.sh` returns a coherent answer, the deploy worked.

## Commands

| Command | Purpose |
|---|---|
| `./deploy.sh` | Stage → push → submit → poll → dump errors. ~6-12 min end-to-end. |
| `./deploy.sh --no-poll` | Submit + exit. Prints `run_id`. Use when you don't want to wait. |
| `./deploy.sh --logs <run_id>` | Re-fetch task output for a past run. |
| `./deploy.sh --push-only` | rsync + workspace import-dir, no job submit. For staging-only changes. |
| `./deploy.sh --status` | Show current endpoint state + last 5 UC model versions. |
| `./smoke_test.sh` | POST a default Sudan query. |
| `./smoke_test.sh "Your prompt"` | POST a custom query. |
| `./smoke_test.sh --raw` | Dump the raw JSON response. |

## Prerequisites (one-time setup)

1. Databricks CLI on `$PATH` (`databricks --version` works).
2. CLI profile `hackathon-test` configured in `~/.databrickscfg`:
   ```
   [hackathon-test]
   host  = https://dbc-7837e492-bc52.cloud.databricks.com
   token = <PAT>
   ```
3. `requirements.txt` exists in this directory (it does — committed).
4. `workspace_config.yml` is configured for Free Edition (it is — committed in `hackathon-orchestrator/`).
5. Workspace path is writable: `/Workspace/Users/ra2724@ic.ac.uk/hackathon/orchestrator-neo4j/` (yours by ownership).
6. UC catalog `workspace`, schema `hackathon`, and Lakebase `unhcr.*` tables exist (set up in earlier session, see `lakebase-unhcr-mirror` memory).
7. **Neo4j knowledge graph is loaded** — the find_skill graph lives on Aura Free
   (`neo4j+s://2a3edbfb…`). Build/refresh it with
   `cd ../neo4j/hackathon-brain && .venv/bin/python -m kg.merge_load` (see this
   project's `README.md`). The endpoint reads `NEO4J_*` from the `agent-secrets`
   scope when `neo4j.inject_plaintext: false` — run `./setup_neo4j_secrets.sh`
   first; with `inject_plaintext: true` (the dry-run default) the creds are baked
   into the endpoint env vars and no scope is needed.

## What `./deploy.sh` does, step by step

1. **Stage** — `rsync -aL` resolves the `skills` symlink (→ `../hackathon-skills`) and copies the orchestrator + sibling modules into `/tmp/hackathon-orchestrator-stage`. Excludes `deploy.sh`, `smoke_test.sh`, `DEPLOY.md`, `tests*`, `lab/`, `__pycache__`.
2. **Push** — `databricks workspace import-dir --overwrite` uploads to `/Workspace/Users/ra2724@ic.ac.uk/hackathon/orchestrator-neo4j/`.
3. **Submit** — `databricks jobs submit --no-wait` with the spec in `deployment/job-spec.json`. The spec declares a serverless v5 environment with `-r requirements.txt` so deps are installed before the kernel starts.
4. **Poll** — Every 60s, prints `state: RUNNING -` or terminal state. Times out after 25 min.
5. **Dump** — On terminal state (TERMINATED/INTERNAL_ERROR/SKIPPED), prints the task-level traceback if any. The error lives in `databricks jobs get-run-output`, not `get-run`.

## Known failure modes

Each of these has happened during the 2026-05-13 stabilisation arc. If you hit one again, the fix is already in the code — usually means a config or pin regressed.

| Failure tell | Cause | Memory entry |
|---|---|---|
| `SIGABRT` at `psycopg.pq.import_from_libpq` (exit 134) | `psycopg-binary` 3.2.x bundled libpq aborts on Standard v5 | [`freeedition-pin-matrix`](../../../../.claude/projects/.../memory/feedback_freeedition_pin_matrix.md) |
| `ImportError: cannot import name 'Capabilities' from 'psycopg'` | `langgraph-checkpoint-postgres` got installed and needs psycopg 3.2 | same — keep `langgraph-checkpoint-postgres` OUT of `requirements.txt` |
| `RestException: CATALOG_DOES_NOT_EXIST: Catalog 'uc_test'` | Hardcoded UC path crept back into `_resolve_uc_model_name` | [`freeedition-deploy-fixes`](../../../../.claude/projects/.../memory/feedback_freeedition_deploy_fixes.md) — read from `_CFG`, never hardcode |
| `RuntimeError: DEPLOY_V3 requires sp-client-id...` | `agent-secrets` scope hard-required again | same — log a warning and fall through to `DATABRICKS_TOKEN` |
| `InvalidParameterValue: Scale to zero must be enabled` | `agents.deploy()` called without `scale_to_zero=True` | same — use `scale_to_zero=` (no `_enabled` suffix) |
| `OperationalError: could not parse network address "...service-direct.privatelink..."` | `_resolve_lakebase_url` returned a CNAME as `hostaddr=` | same — DoH parser must filter for type=1 (A record) only |
| `NameError: name '_lakebase_url' is not defined` in `_init_checkpointer` | Edit to `_init_checkpointer` left dangling references | re-check that `_lakebase_url` is set before the `LakebaseVariableStore` + DuckDB DSN blocks |

If you hit something not in this table: paste the traceback from `./deploy.sh` output and we'll triage.

## Files in this deploy ritual

| File | Purpose |
|---|---|
| `deploy.sh` | Main deploy script (this is the entry point). |
| `smoke_test.sh` | Endpoint smoke test — call after deploy. |
| `DEPLOY.md` | This runbook. |
| `requirements.txt` | The pin matrix that works on Standard v5. Read by Environment panel + jobs spec. |
| `deployment/job-spec.json` | The Databricks Jobs API spec. References the workspace `requirements.txt` and the orchestrator notebook. |
| `workspace_config.yml` | Workspace-specific config (host, catalog, Lakebase URL). Gitignored on purpose — don't commit credentials. |

## Endpoint info

| | |
|---|---|
| UC model | `workspace.hackathon.orchestrator_agent_neo4j` |
| Endpoint name | `agents_workspace-hackathon-orchestrator_agent_neo4j` |
| Workspace | `dbc-7837e492-bc52.cloud.databricks.com` (Free Edition, AWS us-east-2) |
| CLI profile | `hackathon-test` |
| Workspace path | `/Workspace/Users/ra2724@ic.ac.uk/hackathon/orchestrator-neo4j/` |

## Rolling back

There's no rollback script — model versions accumulate in UC and the endpoint serves the latest. To roll back manually:

```bash
# Find the version to roll back to
databricks api get /api/2.1/unity-catalog/models/workspace.hackathon.orchestrator_agent_neo4j/versions --profile hackathon-test

# Update the endpoint to serve that specific version
databricks serving-endpoints update-config agents_workspace-hackathon-orchestrator_agent_neo4j \
  --json '{"served_entities": [{"entity_name": "workspace.hackathon.orchestrator_agent_neo4j", "entity_version": "<N>", "workload_size": "Small", "scale_to_zero_enabled": true}]}' \
  --profile hackathon-test
```

## Tighter iteration tips (during Project Period)

- **Code change only, no config change** → `./deploy.sh` is full ceremony but still the right call. Don't try to skip log_model. Treat each agent edit as a full deploy.
- **`workspace_config.yml` only** → `./deploy.sh --push-only` then re-Apply the environment in the UI; no need to log a new model version.
- **Debug an old failure** → `./deploy.sh --logs <run_id>` re-fetches the task output without redeploying.
- **Just check state** → `./deploy.sh --status` prints endpoint readiness + last 5 model versions.

Don't `Ctrl+C` mid-poll — the deploy keeps running on Databricks even if you kill the script. Re-attach with `./deploy.sh --logs <run_id>` using the run_id from the submit step.

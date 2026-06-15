"""Shared helpers for the prep kit: config loading + SQL warehouse execution.

Connection conventions mirror the orchestrator's ``tools/run_spark_sql.py``
(Statement Execution API, ``wait_timeout`` capped at 50s per the Databricks
constraint) so anything that runs here runs the same way in the live agent.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# --- config -----------------------------------------------------------------

_DEF_CONFIG_NAMES = ("workspace_config.yml", "workspace_config.example.yml")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(path: str | None = None) -> dict:
    """Load workspace_config.yml (falls back to the .example template).

    Env vars always win, so the same code works on a laptop, in a notebook, or
    inside the serving container. Returns a flat dict of the values the prep
    tools need.
    """
    import yaml  # pyyaml ships with the orchestrator deps

    cfg_path: Path | None = None
    if path:
        cfg_path = Path(path)
    else:
        for name in _DEF_CONFIG_NAMES:
            cand = _repo_root() / name
            if cand.exists():
                cfg_path = cand
                break
    raw: dict = {}
    if cfg_path and cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text()) or {}

    db = raw.get("databricks", {}) or {}
    compute = raw.get("compute", {}) or {}
    uc = raw.get("unity_catalog", {}) or {}
    neo = raw.get("neo4j", {}) or {}

    host = (os.environ.get("DATABRICKS_HOST") or db.get("host") or "").strip()
    if host and not host.startswith("http"):
        host = f"https://{host}"

    return {
        "config_path": str(cfg_path) if cfg_path else None,
        "host": host.rstrip("/"),
        "token": (os.environ.get("DATABRICKS_TOKEN") or db.get("token") or "").strip(),
        "warehouse_id": (os.environ.get("SQL_WAREHOUSE_ID")
                         or compute.get("sql_warehouse_id") or "").strip(),
        "catalog": (os.environ.get("HACKATHON_CATALOG")
                    or uc.get("catalog") or "").strip(),
        "neo4j_uri": (os.environ.get("NEO4J_URI") or neo.get("uri") or "").strip(),
        "neo4j_user": (os.environ.get("NEO4J_USER") or neo.get("user") or "").strip(),
        "neo4j_password": (os.environ.get("NEO4J_PASSWORD") or neo.get("password") or "").strip(),
        "neo4j_database": (os.environ.get("NEO4J_DATABASE") or neo.get("database") or "neo4j").strip(),
        "embed_endpoint": (os.environ.get("BRAIN_EMBED_ENDPOINT")
                           or neo.get("embed_endpoint") or "databricks-gte-large-en").strip(),
    }


def make_workspace_client(cfg: dict):
    """Build a databricks.sdk.WorkspaceClient from explicit host/token, falling
    back to the SDK's ambient auth (profile / notebook) when they're absent."""
    from databricks.sdk import WorkspaceClient

    if cfg.get("host") and cfg.get("token"):
        return WorkspaceClient(host=cfg["host"], token=cfg["token"])
    return WorkspaceClient()  # ambient auth (DEFAULT profile / notebook creds)


# --- SQL execution ----------------------------------------------------------

class SqlError(RuntimeError):
    pass


def exec_sql(
    w: Any,
    warehouse_id: str,
    sql: str,
    *,
    wait_timeout: str = "50s",
    poll_timeout_s: int = 240,
    poll_every_s: float = 2.0,
) -> tuple[list[str], list[list], bool]:
    """Run a statement and return (columns, rows, truncated).

    Polls ``get_statement`` past the 50s API cap and follows result chunks so a
    wide INFORMATION_SCHEMA scan comes back complete. Raises ``SqlError`` on a
    FAILED / non-SUCCEEDED terminal state.
    """
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout=wait_timeout,
    )
    deadline = time.time() + poll_timeout_s
    while True:
        state = _state(resp)
        if state in ("PENDING", "RUNNING"):
            if time.time() > deadline:
                raise SqlError(f"statement timed out after {poll_timeout_s}s")
            time.sleep(poll_every_s)
            resp = w.statement_execution.get_statement(resp.statement_id)
            continue
        break

    state = _state(resp)
    if state == "FAILED":
        msg = _err_message(resp) or "unknown SQL error"
        raise SqlError(msg)
    if state != "SUCCEEDED":
        raise SqlError(f"statement ended in state {state}")

    manifest = getattr(resp, "manifest", None)
    schema = getattr(manifest, "schema", None) if manifest else None
    cols_meta = getattr(schema, "columns", None) if schema else None
    columns = [c.name for c in cols_meta] if cols_meta else []

    result = getattr(resp, "result", None)
    rows: list[list] = list(getattr(result, "data_array", None) or []) if result else []
    truncated = bool(getattr(result, "truncated", False)) if result else False

    # follow result chunks (large metadata scans span multiple chunks)
    nxt = getattr(result, "next_chunk_index", None) if result else None
    while nxt is not None:
        chunk = w.statement_execution.get_statement_result_chunk_n(resp.statement_id, nxt)
        rows += list(getattr(chunk, "data_array", None) or [])
        nxt = getattr(chunk, "next_chunk_index", None)

    return columns, rows, truncated


def _state(resp: Any) -> str | None:
    status = getattr(resp, "status", None)
    st = getattr(status, "state", None) if status else None
    return getattr(st, "value", st) if st is not None else None


def _err_message(resp: Any) -> str | None:
    status = getattr(resp, "status", None)
    err = getattr(status, "error", None) if status else None
    return getattr(err, "message", None) if err else None


def ensure_warehouse_running(w: Any, warehouse_id: str, *, wait_s: int = 180) -> None:
    """Best-effort warehouse warm-up. Free Edition serverless warehouses cold
    start; start it and wait briefly so the first profile query doesn't error."""
    try:
        wh = w.warehouses.get(warehouse_id)
        state = getattr(getattr(wh, "state", None), "value", None)
        if state in ("RUNNING",):
            return
        w.warehouses.start(warehouse_id)
        deadline = time.time() + wait_s
        while time.time() < deadline:
            wh = w.warehouses.get(warehouse_id)
            if getattr(getattr(wh, "state", None), "value", None) == "RUNNING":
                return
            time.sleep(5)
    except Exception:
        # Non-fatal: the statement call will surface a clearer error if needed.
        pass


def bt(ident: str) -> str:
    """Backtick-quote a catalog/schema/table/column identifier safely."""
    return "`" + str(ident).replace("`", "``") + "`"


def fq(*parts: str) -> str:
    """Fully-qualified, backtick-quoted ``a.b.c``."""
    return ".".join(bt(p) for p in parts if p)

"""Spark SQL fallback data retrieval tool (plan group A3).

Replaces the v1 ``run_spark_sql`` (``deep_agent_ra/deploy_orchestrator_agent.py``
lines 1164-1255) which returned a 100-row markdown table + JSON dump of
the first 10 rows as a multi-line string. The v2 version stores the
result to the VariableStore and returns a compact pass-by-reference
payload via ``_compact_ref`` — keeping the tool return under ~500 tokens
even for large result sets.

**What was stripped** (v1 source lines 1222-1251):

- ``for row in data[:max_rows]`` markdown table loop
- "... N more rows" tail
- ``json.dumps([dict(zip(columns, row)) for row in data[:10]], indent=2)``
  extra JSON dump of the first 10 rows

**What was kept:**

- Input validation (empty SQL check)
- Warehouse auto-start via ``ensure_warehouse_running``
- Statement Execution API call with 50s wait_timeout (Databricks API cap)
- Auto-store via ``InjectedStore()``
- Error returns for FAILED, non-SUCCEEDED states, and generic exceptions

**Factory pattern:** same as ``ask_genie_space`` — takes ``workspace_client``,
``variable_store_cls``, ``sql_warehouse_id`` as closure args so the tool
is testable without a real Databricks SDK client.

Spec: ``deep_agent_ra_v2/plans/functional-dancing-tiger.md`` A3 (ST §1.3).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Callable

import pandas as pd
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error, _compact_ref
from util.trace_collector import record_sql

logger = logging.getLogger(__name__)


def build_run_spark_sql_tool(
    *,
    workspace_client: Any,
    variable_store_cls: Any,
    sql_warehouse_id: str,
    ensure_warehouse_running: Callable[[Any, str], str | None] | None = None,
    wait_timeout: str = "50s",
):
    """Build the ``run_spark_sql`` tool with dependencies bound.

    Args:
        workspace_client: A ``databricks.sdk.WorkspaceClient`` (or a
            test fake exposing ``.statement_execution.execute_statement``).
        variable_store_cls: The ``VariableStore`` class.
        sql_warehouse_id: Warehouse ID the tool will submit statements to.
        ensure_warehouse_running: Optional callable ``(client, warehouse_id)
            -> error_str | None``. Called before each execute to auto-start
            stopped warehouses. Pass ``None`` to skip the check (tests).
        wait_timeout: Statement Execution API wait_timeout string. MUST be
            "0s" or 5-50 seconds per Databricks constraint — do not exceed
            "50s".
    """

    @tool
    def run_spark_sql(
        sql: str,
        config: RunnableConfig = None,
        store: Annotated[Any, InjectedStore()] = None,
    ) -> str:
        """Execute a Spark SQL query on the Databricks SQL warehouse.

        FALLBACK tool — use ``ask_genie_space`` first for data retrieval.
        Only reach for ``run_spark_sql`` when Genie can't answer (missing
        space, schema not in Genie's scope, or the question explicitly
        asks for a SQL-level operation Genie won't do).

        Results are auto-stored to the VariableStore and returned as a
        COMPACT JSON payload (~500 token budget) with variable_name +
        schema + a 3-row preview. Downstream tools can then operate on
        the full data via ``query_stored_dfs``, ``describe_dataframe``,
        or ``run_python_code``.

        Args:
            sql: A complete SQL SELECT statement. Fully-qualify all
                tables (``catalog.schema.table``).

        Returns:
            JSON string. On success: ``{"status": "ok", ...}`` per the
            compact_ref contract. On failure: ``{"status": "error",
            "error_type", "message", "sql"}``.
        """
        if not sql or not sql.strip():
            return json.dumps(_compact_error("empty_sql", "SQL statement is empty.", sql=sql))

        if workspace_client is None:
            return json.dumps(
                _compact_error("workspace_client_missing", "WorkspaceClient not initialized.", sql=sql)
            )

        if ensure_warehouse_running is not None:
            wh_err = ensure_warehouse_running(workspace_client, sql_warehouse_id)
            if wh_err:
                return json.dumps(_compact_error("warehouse_unavailable", wh_err, sql=sql))

        try:
            response = workspace_client.statement_execution.execute_statement(
                warehouse_id=sql_warehouse_id,
                statement=sql,
                wait_timeout=wait_timeout,
            )
        except Exception as e:
            return json.dumps(_compact_error("statement_api_error", str(e), sql=sql))

        status = getattr(response, "status", None)
        state = (
            getattr(getattr(status, "state", None), "value", None) if status else None
        )

        if state == "FAILED":
            err = getattr(getattr(status, "error", None), "message", None) or "Unknown SQL error"
            return json.dumps(_compact_error("sql_failed", err, sql=sql))

        if state != "SUCCEEDED":
            return json.dumps(
                _compact_error(
                    f"sql_state_{str(state).lower()}",
                    f"SQL status: {state}. Try simplifying the query or retrying.",
                    sql=sql,
                )
            )

        manifest = getattr(response, "manifest", None)
        result = getattr(response, "result", None)
        schema = getattr(manifest, "schema", None) if manifest else None
        schema_cols = getattr(schema, "columns", None) if schema else None
        columns = [c.name for c in schema_cols] if schema_cols else []
        data = getattr(result, "data_array", None) if result else None

        if not columns:
            return json.dumps(
                _compact_error("no_columns", "Query succeeded but returned no columns.", sql=sql)
            )

        # Empty-but-successful queries still return a compact ref so the
        # LLM can see the schema. Zero-row result != error.
        df = pd.DataFrame(data or [], columns=columns)
        var_name = variable_store_cls.auto_name(sql[:60], "spark_sql")

        # Record full SQL for episodic memory (before compact_ref truncates)
        record_sql(sql, source="spark_sql")

        was_overwritten = False
        if store is not None and not df.empty:
            try:
                vs = variable_store_cls(store, config or {})
                vs.store(
                    var_name,
                    df,
                    source="spark_sql",
                    description=sql[:200],
                    query_sql=sql[:500],
                )
                was_overwritten = getattr(vs, "last_was_overwritten", False)
            except Exception as e:
                logger.warning("run_spark_sql auto-store failed: %s", e)

        return json.dumps(
            _compact_ref(
                var_name=var_name,
                source="spark_sql",
                sql=sql,
                df=df,
                was_overwritten=was_overwritten,
            )
        )

    return run_spark_sql

"""DuckDB-over-Lakebase fast path for querying stored DataFrames.

Runs arbitrary SQL against variables previously stored by
``ask_genie_space``, ``run_spark_sql``, or ``store_dataframe`` without
rehydrating pandas. The tool opens a transient DuckDB connection,
``ATTACH``-es the Lakebase Postgres instance via the DuckDB postgres
extension (installed from ``extensions.duckdb.org`` on first use), and
creates a ``CREATE OR REPLACE TEMP VIEW`` per stored variable in the
current ``(user_id, thread_id)`` scope. The user writes SQL that
references variable names directly — the views map them back to the
real ``ai_chatbot.variable_store_<hash>`` tables.

The attach-and-temp-view model was picked by benchmark for its low cold
latency (~0.65x vs. rehydrating pandas on 100K rows). Notable: ~500ms per
call, so the subagent prompts should encourage SQL batching with CTEs
rather than 5 sequential one-liners.

**Result auto-store:** if ``result_name`` is provided and the
VariableStore factory is wired, the result DataFrame is stored back to
Lakebase under the new name so downstream queries can chain on it.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Callable, Optional

import pandas as pd
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error, _compact_ref

logger = logging.getLogger(__name__)


def _quote_view_ident(name: str) -> str:
    """Minimal DuckDB identifier quoting — double-quote + double internal quotes."""
    return '"' + str(name).replace('"', '""') + '"'


def build_query_stored_dfs_tool(
    *,
    variable_store_cls: Any,
    lakebase_dsn: str,
    duckdb_connect: Optional[Callable[..., Any]] = None,
    schema: str = "ai_chatbot",
    attach_alias: str = "lake",
    install_extension: bool = True,
):
    """Build the ``query_stored_dfs`` tool with deps bound.

    Args:
        variable_store_cls: VariableStore class whose
            ``(store, config)``-constructed instance exposes ``store()``
            and ``auto_name()``. Used only when ``result_name`` is
            provided by the caller OR to generate a default name.
        lakebase_dsn: DuckDB-postgres ATTACH DSN. Format:
            ``dbname=databricks_postgres host=<gw-ip> user=chatbot_svc
            password=<pw> sslmode=require``. No trailing semicolon.
        duckdb_connect: Override for ``duckdb.connect`` (tests pass a
            fake). Default: imports ``duckdb`` lazily and uses
            ``duckdb.connect``.
        schema: Postgres schema name where ``variable_store_*`` tables
            live. Default: ``ai_chatbot``.
        attach_alias: Alias used for the ATTACH'd database inside
            DuckDB. Default: ``lake``.
        install_extension: If True, runs ``INSTALL postgres; LOAD
            postgres;`` at the start of every call. Set False for tests
            where the fake connection doesn't support extensions.
    """

    if duckdb_connect is None:
        def _default_connect():
            import duckdb
            return duckdb.connect(":memory:")
        duckdb_connect = _default_connect

    @tool
    def query_stored_dfs(
        sql: str,
        result_name: Optional[str] = None,
        config: RunnableConfig = None,
        store: Annotated[Any, InjectedStore()] = None,
    ) -> str:
        """Run SQL against stored DataFrames via DuckDB.

        Use AFTER ``ask_genie_space`` / ``run_spark_sql`` have populated the
        VariableStore. Reference stored variables by name as tables (e.g.
        ``SELECT state, SUM(facility_count) FROM facilities_by_district GROUP BY 1``).
        DuckDB dialect; joins, window functions and CTEs all work. Prefer ONE
        multi-stage CTE query over several one-liners — each call costs ~500ms
        of attach overhead.

        Args:
            sql: DuckDB SQL referencing stored variable names as tables.
            result_name: Optional snake_case name to auto-store the result for
                chaining; if None the result is not persisted (you still get
                the compact preview).

        Returns:
            JSON string — compact ref ``{status, variable_name, schema,
            row_count, preview_rows, ...}`` on success, error payload on failure.
        """
        if not sql or not sql.strip():
            return json.dumps(_compact_error("empty_sql", "SQL statement is empty.", sql=sql))

        cfg: dict = {}
        if config is not None:
            cfg = (config or {}).get("configurable", {}) or {}
        user_id = str(cfg.get("user_id", "default_user"))
        thread_id = str(cfg.get("thread_id", "default_thread"))

        con = None
        try:
            con = duckdb_connect()

            if install_extension:
                con.execute("INSTALL postgres")
                con.execute("LOAD postgres")

                attach_sql = (
                    f"ATTACH '{lakebase_dsn}' AS {_quote_view_ident(attach_alias)} "
                    f"(TYPE postgres, SCHEMA '{schema}')"
                )
                con.execute(attach_sql)

                # Enumerate stored variables in this scope and create DuckDB
                # temp views that map variable name → real Lakebase table.
                try:
                    index_rows = con.execute(
                        f"SELECT name, table_name FROM {_quote_view_ident(attach_alias)}.variable_store_index "
                        f"WHERE user_id = ? AND thread_id = ?",
                        [user_id, thread_id],
                    ).fetchall()
                except Exception as e:
                    # Index table may not exist yet (fresh deploy) — still
                    # let the user issue raw SQL against lake.* if they
                    # know the hash names.
                    logger.warning("query_stored_dfs: index enumeration failed: %s", e)
                    index_rows = []

                for var_name, table_name in index_rows:
                    view_sql = (
                        f"CREATE OR REPLACE TEMP VIEW {_quote_view_ident(var_name)} AS "
                        f"SELECT * FROM {_quote_view_ident(attach_alias)}.{_quote_view_ident(table_name)}"
                    )
                    try:
                        con.execute(view_sql)
                    except Exception as e:
                        logger.warning("query_stored_dfs: view creation failed for %s: %s", var_name, e)

            result = con.execute(sql).df()

        except Exception as e:
            return json.dumps(_compact_error("duckdb_error", str(e), sql=sql))
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:
                    pass

        # Determine the variable name for the return payload. If the
        # caller passed result_name and auto-store succeeds, use that.
        # Otherwise fall back to an auto-generated name so the compact
        # ref has something to display.
        final_name = result_name
        was_overwritten = False
        if result_name and store is not None:
            try:
                vs = variable_store_cls(store, config or {})
                vs.store(
                    result_name,
                    result,
                    source="query_stored_dfs",
                    description=sql[:200],
                    query_sql=sql[:500],
                )
                was_overwritten = getattr(vs, "last_was_overwritten", False)
            except Exception as e:
                logger.warning("query_stored_dfs auto-store failed: %s", e)

        if not final_name:
            try:
                final_name = variable_store_cls.auto_name(sql[:60], "query_stored_dfs")
            except Exception:
                final_name = "query_result"

        return json.dumps(
            _compact_ref(
                var_name=final_name,
                source="query_stored_dfs",
                sql=sql,
                df=result if isinstance(result, pd.DataFrame) else pd.DataFrame(result),
                was_overwritten=was_overwritten,
            )
        )

    return query_stored_dfs

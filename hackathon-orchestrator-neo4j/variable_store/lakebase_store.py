"""Lakebase-native VariableStore (plan groups A6b + A8).

Replaces the v1 ``VariableStore`` class (``deep_agent_ra/deploy_orchestrator_agent.py``
lines 545-756) which stored DataFrames as JSON blobs inside the LangGraph
``PostgresStore`` with a Volumes-Parquet durability fallback. The v2
class writes each DataFrame as a real Postgres table and keeps metadata
in a new ``ai_chatbot.variable_store_index`` lookup table. No JSON, no
Parquet, no LangGraph store dependency on the read path — Postgres IS
the durability.

**Why:** A6a benchmark (see ``benchmarks/duckdb_model_comparison.py``,
commit ``3282764``) showed median ``C/A_cold`` = 0.65x on 100K rows —
Model C (DuckDB ATTACH Postgres) beats the v1 JSON rehydrate path by
35% on cold reads AND unlocks SQL-level queries across stored DFs via
``query_stored_dfs`` (plan A6).

**Scoping:** Tables are named ``variable_store_<sha1(user_id::thread_id::name)[:12]>``.
The scope triple is part of the hash so two users with the same
``name`` don't collide on the same Postgres table. The v1 class used
LangGraph store namespaces for scoping — we preserve that boundary by
encoding it into the table name instead.

**Concurrency:** every ``store()`` call runs DROP-CREATE-COPY-UPSERT as
a single transaction, so concurrent writers to the same
``(user_id, thread_id, name)`` slot serialize on the DDL lock. Different
slots are fully parallel.

**NaN/Inf handling:** COPY chokes on non-finite floats. The sanitizer
replaces ``NaN``/``±Inf`` with ``NULL`` before the COPY. This matches
the v1 ``_sanitize_df_for_json`` behavior documented in
``deep_agent_ra/CLAUDE.md`` under "Databricks Platform Constraints".

**Compatibility:** the class accepts v1's ``(store, config)`` constructor
signature so the tool factories in ``tools/ask_genie_space.py`` +
``tools/run_spark_sql.py`` can keep using ``variable_store_cls(store,
config)`` unchanged. The ``store`` arg is ignored (kept for signature
compat); ``config`` still provides ``user_id`` / ``thread_id``. The
Postgres connection comes from a module-level ``_CONFIG`` set by
``configure(connection_factory=...)`` at deploy time.

Spec: ``deep_agent_ra_v2/plans/functional-dancing-tiger.md`` A6b + A8.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level config
# ---------------------------------------------------------------------------

_CONFIG: Dict[str, Any] = {
    "connection_factory": None,
    "schema": "ai_chatbot",
}


def configure(
    *,
    connection_factory: Callable[[], Any],
    schema: str = "ai_chatbot",
) -> None:
    """Wire up the module-level Postgres connection factory.

    Called once at deploy-notebook startup (B3 will land this call in
    Cell 6 of ``deploy_orchestrator_agent.py``). Until ``configure`` is
    called, ``LakebaseVariableStore(store, config)`` will raise on
    construction — fail-fast, same policy as v1's hard-fail on missing
    Lakebase URL.

    Args:
        connection_factory: Zero-arg callable returning a live
            ``psycopg.Connection`` (or a connection-pool proxy). Called
            at the start of every public method.
        schema: Postgres schema name. Defaults to the shared
            ``ai_chatbot`` schema used by the Node.js chat app.
    """
    _CONFIG["connection_factory"] = connection_factory
    _CONFIG["schema"] = schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_name(user_id: str, thread_id: str, name: str) -> str:
    """Deterministic Postgres table name scoped by (user, thread, name).

    12 hex chars = 48 bits = ~2.8e14 combinations. Collision probability
    is negligible at our scale (~10K stored DFs per user). The input
    delimiter ``::`` is chosen because it cannot appear in a Postgres
    user_id or thread_id (both are UUID/email-shaped).
    """
    h = hashlib.sha1(f"{user_id}::{thread_id}::{name}".encode()).hexdigest()[:12]
    return f"variable_store_{h}"


def _pg_type_for(dtype: Any) -> str:
    """Map a pandas dtype to a Postgres column type.

    Anything we don't explicitly recognize falls back to TEXT, which
    stringifies unknown types via ``_sanitize_value``. Not perfect but
    deterministic and lossless for serialization-only use.
    """
    s = str(dtype).lower()
    if s.startswith(("int", "uint")):
        return "BIGINT"
    if s.startswith("float"):
        return "DOUBLE PRECISION"
    if s == "bool":
        return "BOOLEAN"
    if s.startswith("datetime64"):
        return "TIMESTAMPTZ" if ("utc" in s or "tz" in s or "," in s) else "TIMESTAMP"
    return "TEXT"


def _sanitize_value(v: Any) -> Any:
    """Coerce a pandas cell value into something psycopg COPY accepts.

    - ``NaN``/``±Inf`` → None (Postgres NULL) — COPY rejects non-finite floats.
    - ``pd.NA`` / ``pd.NaT`` → None.
    - Native Python scalars pass through.
    - Anything else (dict, list, complex, custom) gets ``str()``-ified.
    """
    if v is None:
        return None
    # pd.NA / pd.NaT and numpy NaN handling
    try:
        if pd.isna(v):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        # pd.isna raises on some array-likes; fall through
        pass
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, (bool, int, str, bytes)):
        return v
    if isinstance(v, (datetime, date)):
        return v
    # Fallback: dict, list, tuple, complex, custom — stringify.
    return str(v)


def _quote_ident(name: str) -> str:
    """Double-quote + escape a Postgres identifier.

    Postgres identifiers can be quoted with ``"..."`` which preserves
    case and allows arbitrary characters. Internal double-quotes are
    escaped by doubling: ``"foo""bar"``.
    """
    return '"' + str(name).replace('"', '""') + '"'


def _create_table_ddl(schema: str, table: str, df: pd.DataFrame) -> str:
    """Build a ``CREATE TABLE`` statement matching the DataFrame schema."""
    cols = [
        f"{_quote_ident(str(c))} {_pg_type_for(df.dtypes[c])}"
        for c in df.columns
    ]
    return (
        f"CREATE TABLE {_quote_ident(schema)}.{_quote_ident(table)} "
        f"({', '.join(cols)})"
    )


def _serializable(v: Any) -> Any:
    """Convert a value into something json.dumps can handle. For use on
    ``.describe()`` stats + sample rows that go back to the LLM.
    """
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", errors="replace")
        except Exception:
            return str(v)
    try:
        if pd.isna(v):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


# ---------------------------------------------------------------------------
# LakebaseVariableStore
# ---------------------------------------------------------------------------


class LakebaseVariableStore:
    """VariableStore backed by real Postgres tables in Lakebase.

    Each stored DataFrame becomes its own Postgres table under
    ``ai_chatbot.variable_store_<hash>``. Metadata lives in
    ``ai_chatbot.variable_store_index`` keyed on
    ``(user_id, thread_id, name)``.

    Two invocation styles:

    1. From tool factories (v1-compat)::

           vs = LakebaseVariableStore(store, config)

       ``store`` is ignored. ``config`` provides ``user_id`` and
       ``thread_id``. Connection comes from ``_CONFIG`` (set by
       ``configure`` at startup).

    2. From tests / explicit use::

           vs = LakebaseVariableStore(
               connection_factory=lambda: my_conn,
               user_id="u1",
               thread_id="t1",
           )

       Direct deps; no module state needed.
    """

    def __init__(
        self,
        store: Any = None,
        config: Any = None,
        *,
        connection_factory: Optional[Callable[[], Any]] = None,
        schema: Optional[str] = None,
        user_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ):
        self._conn_factory = connection_factory or _CONFIG["connection_factory"]
        self._schema = schema or _CONFIG["schema"]

        if user_id is not None and thread_id is not None:
            self._user_id = str(user_id)
            self._thread_id = str(thread_id)
        else:
            cfg: dict = {}
            if config is not None:
                cfg = (config or {}).get("configurable", {}) or {}
            self._user_id = str(cfg.get("user_id", "default_user"))
            self._thread_id = str(cfg.get("thread_id", "default_thread"))

        # Set by store() — tools read this to surface overwrite notices.
        self.last_was_overwritten: bool = False

        if self._conn_factory is None:
            raise RuntimeError(
                "LakebaseVariableStore has no connection_factory. Call "
                "variable_store.lakebase_store.configure(connection_factory=...) "
                "at deploy startup, or pass connection_factory= to the constructor."
            )

    # ----- internal helpers --------------------------------------------------

    def _table_name_for(self, name: str) -> str:
        return _table_name(self._user_id, self._thread_id, name)

    def _get_conn(self):
        return self._conn_factory()

    def _schema_sql(self) -> str:
        return _quote_ident(self._schema)

    def _index_sql(self) -> str:
        return f"{self._schema_sql()}.{_quote_ident('variable_store_index')}"

    def _ensure_index_table(self, conn) -> None:
        """Idempotent ``CREATE TABLE IF NOT EXISTS`` for the metadata index."""
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self._index_sql()} (
            user_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            name TEXT NOT NULL,
            table_name TEXT NOT NULL,
            source TEXT,
            query_sql TEXT,
            description TEXT,
            row_count BIGINT,
            schema_json JSONB,
            metadata_json JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, thread_id, name)
        )
        """
        with conn.cursor() as cur:
            cur.execute(ddl)

    # ----- public API --------------------------------------------------------

    def store(
        self,
        name: str,
        df: pd.DataFrame,
        *,
        source: str = "",
        description: str = "",
        query_sql: str = "",
        metadata: Optional[dict] = None,
    ) -> str:
        """Persist ``df`` to Postgres and upsert the index row.

        Returns a short confirmation string for the LLM. Raises on
        unrecoverable errors (connection lost, permission denied, etc.)
        — the tool factories catch and log these.
        """
        conn = self._get_conn()
        try:
            self._ensure_index_table(conn)
            table = self._table_name_for(name)
            full_table = f"{self._schema_sql()}.{_quote_ident(table)}"

            schema_list = [
                {"name": str(c), "dtype": str(df.dtypes[c])}
                for c in df.columns
            ]
            schema_json = json.dumps(schema_list)

            with conn.cursor() as cur:
                # Was there a prior value under this (scope, name)? Tools read
                # self.last_was_overwritten after store() to surface it to the LLM.
                cur.execute(
                    f"SELECT 1 FROM {self._index_sql()} "
                    f"WHERE user_id = %s AND thread_id = %s AND name = %s",
                    (self._user_id, self._thread_id, name),
                )
                self.last_was_overwritten = cur.fetchone() is not None

                # Atomic DROP + CREATE (same transaction as COPY + UPSERT).
                cur.execute(f"DROP TABLE IF EXISTS {full_table}")
                cur.execute(_create_table_ddl(self._schema, table, df))

                if not df.empty:
                    col_list = ", ".join(
                        _quote_ident(str(c)) for c in df.columns
                    )
                    copy_sql = f"COPY {full_table} ({col_list}) FROM STDIN"
                    with cur.copy(copy_sql) as copy:
                        for row in df.itertuples(index=False, name=None):
                            copy.write_row(
                                [_sanitize_value(v) for v in row]
                            )

                cur.execute(
                    f"""
                    INSERT INTO {self._index_sql()}
                        (user_id, thread_id, name, table_name, source,
                         query_sql, description, row_count, schema_json,
                         metadata_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                    ON CONFLICT (user_id, thread_id, name) DO UPDATE SET
                        table_name = EXCLUDED.table_name,
                        source = EXCLUDED.source,
                        query_sql = EXCLUDED.query_sql,
                        description = EXCLUDED.description,
                        row_count = EXCLUDED.row_count,
                        schema_json = EXCLUDED.schema_json,
                        metadata_json = EXCLUDED.metadata_json,
                        created_at = NOW()
                    """,
                    (
                        self._user_id,
                        self._thread_id,
                        name,
                        table,
                        source,
                        query_sql,
                        description,
                        int(len(df)),
                        schema_json,
                        json.dumps(metadata or {}),
                    ),
                )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

        preview_cols = ", ".join(str(c) for c in list(df.columns)[:6])
        if len(df.columns) > 6:
            preview_cols += "..."
        return (
            f"Stored '{name}': {df.shape[0]} rows x {df.shape[1]} cols "
            f"[{preview_cols}]"
        )

    def get(self, name: str) -> Optional[pd.DataFrame]:
        """Return the full stored DataFrame, or ``None`` if not found."""
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT table_name FROM {self._index_sql()} "
                f"WHERE user_id = %s AND thread_id = %s AND name = %s",
                (self._user_id, self._thread_id, name),
            )
            row = cur.fetchone()
            if row is None:
                return None
            stored_table = row[0]
            cur.execute(
                f"SELECT * FROM {self._schema_sql()}.{_quote_ident(stored_table)}"
            )
            data = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return pd.DataFrame(data, columns=cols)

    def preview(self, name: str, n: int = 3) -> Optional[pd.DataFrame]:
        """Return the first ``n`` rows of the stored DataFrame (plan A8).

        Cheap path — does not pull the whole table. Used by
        ``_compact_ref`` (indirectly via the tool factories) and by
        ``describe_dataframe``.
        """
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT table_name FROM {self._index_sql()} "
                f"WHERE user_id = %s AND thread_id = %s AND name = %s",
                (self._user_id, self._thread_id, name),
            )
            row = cur.fetchone()
            if row is None:
                return None
            stored_table = row[0]
            cur.execute(
                f"SELECT * FROM {self._schema_sql()}.{_quote_ident(stored_table)} LIMIT %s",
                (int(n),),
            )
            data = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return pd.DataFrame(data, columns=cols)

    def describe(
        self,
        name: str,
        *,
        stats_sample_size: int = 1000,
    ) -> Optional[Dict[str, Any]]:
        """Return ``{schema, row_count, stats, sample, ...}`` for a DataFrame.

        Backs the ``describe_dataframe`` tool (plan A4). ``stats`` is
        computed from a LIMIT-sampled batch (default 1000 rows) — the
        full-table stats would require pushing aggregates to SQL, which
        is out of scope for Commit 4. For tables smaller than
        ``stats_sample_size`` the stats are exact.
        """
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT table_name, row_count, schema_json, source, description, query_sql "
                f"FROM {self._index_sql()} "
                f"WHERE user_id = %s AND thread_id = %s AND name = %s",
                (self._user_id, self._thread_id, name),
            )
            idx_row = cur.fetchone()
            if idx_row is None:
                return None
            stored_table, row_count, schema_json, source, desc, query_sql = idx_row

            cur.execute(
                f"SELECT * FROM {self._schema_sql()}.{_quote_ident(stored_table)} LIMIT %s",
                (int(stats_sample_size),),
            )
            data = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []

        df_sample = pd.DataFrame(data, columns=cols)

        # Stats — pandas .describe() handles mixed dtypes well with include="all".
        stats: Dict[str, Dict[str, Any]] = {}
        if not df_sample.empty:
            try:
                stats_df = df_sample.describe(include="all")
                for col in stats_df.columns:
                    col_stats = {}
                    for stat_name, v in stats_df[col].items():
                        s = _serializable(v)
                        if s is not None:
                            col_stats[str(stat_name)] = s
                    if col_stats:
                        stats[str(col)] = col_stats
            except Exception as e:
                logger.warning("describe() stats computation failed: %s", e)

        try:
            schema = json.loads(schema_json) if schema_json else []
        except Exception:
            schema = []

        sample_rows: List[Dict[str, Any]] = []
        for _, row in df_sample.head(3).iterrows():
            sample_rows.append(
                {str(k): _serializable(v) for k, v in row.items()}
            )

        return {
            "status": "ok",
            "variable_name": name,
            "source": source or "",
            "description": desc or "",
            "query_sql": query_sql or "",
            "schema": schema,
            "row_count": int(row_count) if row_count is not None else len(df_sample),
            "stats": stats,
            "sample": sample_rows,
            "stats_sample_size": min(int(stats_sample_size), len(df_sample)),
        }

    def list_all(self) -> List[Dict[str, Any]]:
        """List every stored DataFrame in this ``(user_id, thread_id)`` namespace.

        Returns a list of dicts in v1-compatible shape so existing tool
        code that reads ``list_all()`` output (``list_dataframes``)
        doesn't need to change.
        """
        conn = self._get_conn()
        rows: List[Any] = []
        with conn.cursor() as cur:
            try:
                cur.execute(
                    f"SELECT name, source, description, row_count, schema_json, created_at "
                    f"FROM {self._index_sql()} "
                    f"WHERE user_id = %s AND thread_id = %s "
                    f"ORDER BY created_at DESC",
                    (self._user_id, self._thread_id),
                )
                rows = cur.fetchall()
            except Exception as e:
                # Index table may not exist on a fresh deploy — return empty.
                logger.warning("list_all() index query failed: %s", e)
                return []

        results: List[Dict[str, Any]] = []
        now = datetime.now()
        for name, source, description, row_count, schema_json, created_at in rows:
            try:
                schema = json.loads(schema_json) if schema_json else []
            except Exception:
                schema = []
            cols = [s.get("name", "") for s in schema]
            dtypes = {s.get("name", ""): s.get("dtype", "") for s in schema}
            age_min: Optional[float] = None
            if isinstance(created_at, datetime):
                try:
                    age_min = round((now - created_at.replace(tzinfo=None)).total_seconds() / 60, 1)
                except Exception:
                    age_min = None
            results.append(
                {
                    "name": name,
                    "rows": int(row_count) if row_count is not None else 0,
                    "cols": len(cols),
                    "columns": cols,
                    "dtypes": dtypes,
                    "source": source or "",
                    "description": description or "",
                    "age_min": age_min,
                    "accesses": 0,  # Lakebase store doesn't track access counts
                    "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
                }
            )
        return results

    def delete(self, name: str) -> bool:
        """Drop the stored table and remove the index row. Returns True
        if something was deleted, False if nothing was stored under ``name``.
        """
        conn = self._get_conn()
        try:
            table = self._table_name_for(name)
            with conn.cursor() as cur:
                cur.execute(
                    f"DROP TABLE IF EXISTS {self._schema_sql()}.{_quote_ident(table)}"
                )
                cur.execute(
                    f"DELETE FROM {self._index_sql()} "
                    f"WHERE user_id = %s AND thread_id = %s AND name = %s",
                    (self._user_id, self._thread_id, name),
                )
                deleted = cur.rowcount if hasattr(cur, "rowcount") else 1
            conn.commit()
            return bool(deleted)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def clear(self) -> int:
        """Drop every table in this namespace. Returns the count deleted."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT name, table_name FROM {self._index_sql()} "
                    f"WHERE user_id = %s AND thread_id = %s",
                    (self._user_id, self._thread_id),
                )
                rows = cur.fetchall() or []
                for _name, table in rows:
                    cur.execute(
                        f"DROP TABLE IF EXISTS {self._schema_sql()}.{_quote_ident(table)}"
                    )
                cur.execute(
                    f"DELETE FROM {self._index_sql()} "
                    f"WHERE user_id = %s AND thread_id = %s",
                    (self._user_id, self._thread_id),
                )
            conn.commit()
            return len(rows)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    @staticmethod
    def auto_name(question: str, space_id: str = "") -> str:
        """Deterministic-ish short variable name from a question string.

        Copied verbatim from v1 ``VariableStore.auto_name`` (line 751).
        Keeps the same hash suffix shape so upstream LLM prompts that
        reference auto-named variables are unchanged.
        """
        words = [w.lower() for w in question.split() if len(w) > 2 and w.isalpha()][:3]
        base = "_".join(words) if words else "result"
        suffix = hashlib.md5(
            f"{question}{space_id}{time.time()}".encode()
        ).hexdigest()[:6]
        return f"{base}_{suffix}"

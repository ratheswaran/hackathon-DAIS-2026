"""VariableStore package (plan group A6b).

Postgres-native replacement for the v1 in-memory + Volumes-Parquet
VariableStore. The benchmark decision (A6a, 2026-04-12) picked Model C
(DuckDB ``ATTACH`` postgres) on the read path and Lakebase-native psycopg
``COPY`` on the write path, so the store writes DataFrames as real
Postgres tables in ``ai_chatbot.variable_store_<sha1(user::thread::name)[:12]>``
and exposes them for direct SQL query via ``query_stored_dfs``.

Public API:

- ``LakebaseVariableStore`` — the class, drop-in replacement for v1.
- ``configure(connection_factory=...)`` — module-level setter so the
  tool factories can stay ignorant of psycopg.
"""

from variable_store.lakebase_store import (
    LakebaseVariableStore,
    configure,
)

__all__ = ["LakebaseVariableStore", "configure"]

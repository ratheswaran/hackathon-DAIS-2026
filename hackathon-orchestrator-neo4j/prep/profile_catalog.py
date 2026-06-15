"""Profile a Unity Catalog catalog into a JSON + Markdown report.

Day-of usage (the hackathon dataset name contains the event id, e.g. dais_2026):

    python -m prep.profile_catalog --catalog dais_2026 --out prep/out

What it captures, per table:
  * row count, column dtypes, comments
  * non-null %, approximate distinct count (cardinality) per column
  * min / max for numeric + date/timestamp columns
  * top categorical values for low-cardinality string columns
  * 3 sample rows
And across the catalog:
  * candidate join keys (same-named high-cardinality columns shared by >=2 tables,
    plus *_id / iso3 / year / code-style keys)
  * STRING-but-numeric "cast before aggregation" gotcha columns
  * constant / all-null columns

Everything is one cheap aggregate pass per table over the SQL warehouse, capped
and chunked so it stays inside Free Edition limits. Pure read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from prep._common import (SqlError, bt, ensure_warehouse_running, exec_sql, fq,
                          load_config, make_workspace_client)

_NUMERIC_TYPES = {"tinyint", "smallint", "int", "integer", "bigint", "long",
                  "float", "double", "real", "decimal", "numeric"}
_TEMPORAL_TYPES = {"date", "timestamp", "timestamp_ntz"}
_STRINGY_TYPES = {"string", "varchar", "char"}
_NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
_KEYISH = re.compile(r"(^|_)(id|code|key|iso3?|iso2|year|cc|country|fk)$", re.I)


def _base_type(data_type: str) -> str:
    """'decimal(10,2)' -> 'decimal'; 'STRING' -> 'string'."""
    return re.split(r"[(< ]", (data_type or "").strip().lower(), 1)[0]


def list_tables(w, wh, catalog: str, schema: str | None) -> list[dict]:
    where = "WHERE table_schema <> 'information_schema'"
    if schema:
        where = f"WHERE table_schema = '{schema}'"
    sql = (f"SELECT table_schema, table_name, table_type, comment "
           f"FROM {bt(catalog)}.information_schema.tables {where} "
           f"ORDER BY table_schema, table_name")
    cols, rows, _ = exec_sql(w, wh, sql)
    idx = {c: i for i, c in enumerate(cols)}
    return [{"schema": r[idx["table_schema"]], "table": r[idx["table_name"]],
             "table_type": r[idx.get("table_type", 2)],
             "comment": r[idx["comment"]] if "comment" in idx else None}
            for r in rows]


def list_columns(w, wh, catalog: str, schema: str | None) -> dict[tuple, list[dict]]:
    where = "WHERE table_schema <> 'information_schema'"
    if schema:
        where = f"WHERE table_schema = '{schema}'"
    sql = (f"SELECT table_schema, table_name, column_name, data_type, "
           f"is_nullable, ordinal_position, comment "
           f"FROM {bt(catalog)}.information_schema.columns {where} "
           f"ORDER BY table_schema, table_name, ordinal_position")
    cols, rows, _ = exec_sql(w, wh, sql)
    idx = {c: i for i, c in enumerate(cols)}
    out: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r[idx["table_schema"]], r[idx["table_name"]])
        out.setdefault(key, []).append({
            "name": r[idx["column_name"]],
            "data_type": r[idx["data_type"]],
            "base_type": _base_type(r[idx["data_type"]]),
            "nullable": str(r[idx["is_nullable"]]).upper() in ("YES", "TRUE", "1"),
            "comment": r[idx["comment"]] if "comment" in idx else None,
        })
    return out


def profile_table(w, wh, catalog: str, schema: str, table: str, columns: list[dict],
                  *, max_agg_cols: int, top_k_cats: int, sample_rows: int) -> dict:
    tname = fq(catalog, schema, table)
    out: dict = {"schema": schema, "table": table, "row_count": None,
                 "columns": [], "errors": []}

    # 1) row count
    try:
        _, rows, _ = exec_sql(w, wh, f"SELECT COUNT(*) AS n FROM {tname}")
        out["row_count"] = int(rows[0][0]) if rows and rows[0][0] is not None else 0
    except SqlError as e:
        out["errors"].append(f"row_count: {e}")
        return out
    n = out["row_count"] or 0

    # 2) per-column aggregates, chunked. positional aliases dodge weird names.
    col_stats: dict[str, dict] = {c["name"]: dict(c) for c in columns}
    for chunk_start in range(0, len(columns), max_agg_cols):
        chunk = columns[chunk_start:chunk_start + max_agg_cols]
        exprs: list[str] = []
        for i, c in enumerate(chunk):
            gi = chunk_start + i
            col = bt(c["name"])
            exprs.append(f"COUNT({col}) AS nn_{gi}")
            exprs.append(f"approx_count_distinct({col}) AS nd_{gi}")
            if c["base_type"] in _NUMERIC_TYPES or c["base_type"] in _TEMPORAL_TYPES:
                exprs.append(f"CAST(MIN({col}) AS STRING) AS mn_{gi}")
                exprs.append(f"CAST(MAX({col}) AS STRING) AS mx_{gi}")
            if c["base_type"] in _STRINGY_TYPES:
                # how many non-null values look numeric -> "cast before agg" gotcha
                exprs.append(
                    f"SUM(CASE WHEN {col} IS NOT NULL AND "
                    f"{col} RLIKE '^-?[0-9]+(\\\\.[0-9]+)?$' THEN 1 ELSE 0 END) AS num_{gi}")
                exprs.append(f"MAX(LENGTH({col})) AS len_{gi}")
        if not exprs:
            continue
        sql = f"SELECT {', '.join(exprs)} FROM {tname}"
        try:
            cols, rows, _ = exec_sql(w, wh, sql)
        except SqlError as e:
            out["errors"].append(f"agg[{chunk_start}]: {e}")
            continue
        idx = {c: i for i, c in enumerate(cols)}
        row = rows[0] if rows else []

        def g(alias):
            i = idx.get(alias)
            return row[i] if (i is not None and i < len(row)) else None

        for i, c in enumerate(chunk):
            gi = chunk_start + i
            name = c["name"]
            st = col_stats[name]
            nn = _to_int(g(f"nn_{gi}"))
            nd = _to_int(g(f"nd_{gi}"))
            st["non_null"] = nn
            st["null_pct"] = round(100.0 * (n - (nn or 0)) / n, 1) if n else None
            st["distinct_approx"] = nd
            if g(f"mn_{gi}") is not None or g(f"mx_{gi}") is not None:
                st["min"] = g(f"mn_{gi}")
                st["max"] = g(f"mx_{gi}")
            if c["base_type"] in _STRINGY_TYPES:
                num = _to_int(g(f"num_{gi}")) or 0
                st["max_len"] = _to_int(g(f"len_{gi}"))
                st["numeric_string_ratio"] = round(num / nn, 3) if nn else 0.0

    # 3) top categorical values for low-cardinality string columns
    cat_budget = 0
    for name, st in col_stats.items():
        if cat_budget >= 8:
            break
        if (st["base_type"] in _STRINGY_TYPES and (st.get("distinct_approx") or 0)
                and st["distinct_approx"] <= 50 and (st.get("numeric_string_ratio") or 0) < 0.5):
            col = bt(name)
            try:
                _, rows, _ = exec_sql(
                    w, wh,
                    f"SELECT {col} AS v, COUNT(*) AS c FROM {tname} "
                    f"WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY c DESC LIMIT {top_k_cats}")
                st["top_values"] = [{"value": r[0], "count": _to_int(r[1])} for r in rows]
                cat_budget += 1
            except SqlError as e:
                out["errors"].append(f"top[{name}]: {e}")

    # 4) sample rows
    try:
        cols, rows, _ = exec_sql(w, wh, f"SELECT * FROM {tname} LIMIT {sample_rows}")
        out["sample_columns"] = cols
        out["sample_rows"] = rows
    except SqlError as e:
        out["errors"].append(f"sample: {e}")

    # 5) per-column flags
    for name, st in col_stats.items():
        flags = []
        if (st.get("numeric_string_ratio") or 0) >= 0.9 and st["base_type"] in _STRINGY_TYPES:
            flags.append("string-numeric (CAST to DOUBLE before aggregating)")
        if st.get("distinct_approx") == 1:
            flags.append("constant")
        if (st.get("null_pct") or 0) == 100.0:
            flags.append("all-null")
        elif (st.get("null_pct") or 0) >= 80.0:
            flags.append("mostly-null")
        if _KEYISH.search(name) or (n and st.get("distinct_approx") and st["distinct_approx"] >= 0.9 * n):
            flags.append("key-like")
        if st["base_type"] in _TEMPORAL_TYPES or re.search(r"(^|_)year$", name, re.I):
            flags.append("temporal")
        st["flags"] = flags
        out["columns"].append(st)

    # primary-key guess: a single near-unique non-null column
    pk = next((c["name"] for c in out["columns"]
               if n and c.get("distinct_approx") and c["distinct_approx"] >= 0.98 * n
               and (c.get("null_pct") or 0) == 0.0), None)
    out["primary_key_guess"] = pk
    return out


def find_join_keys(tables: list[dict]) -> list[dict]:
    """Same-named columns that look like keys and appear in >= 2 tables."""
    by_col: dict[str, list[tuple]] = {}
    for t in tables:
        for c in t.get("columns", []):
            if "key-like" in c.get("flags", []):
                by_col.setdefault(c["name"].lower(), []).append((t["schema"], t["table"]))
    joins = []
    for col, locs in sorted(by_col.items()):
        if len(locs) >= 2:
            joins.append({"column": col, "tables": [f"{s}.{t}" for s, t in locs]})
    return joins


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --- report rendering -------------------------------------------------------

def render_markdown(profile: dict) -> str:
    L = [f"# Catalog profile — `{profile['catalog']}`",
         f"_generated {profile['generated_at']} · {len(profile['tables'])} tables · "
         f"warehouse `{profile['warehouse_id']}`_", ""]

    gotchas = profile["summary"]["string_numeric_columns"]
    if gotchas:
        L += ["## ⚠ String-numeric columns (CAST before aggregation)",
              "These look like the `ANP_Paid`/`CASE_Paid` gotcha — stored as STRING but numeric:", ""]
        for g in gotchas:
            L.append(f"- `{g['table']}`.`{g['column']}` — {int(g['numeric_string_ratio']*100)}% numeric")
        L.append("")

    joins = profile["summary"]["candidate_join_keys"]
    if joins:
        L += ["## Candidate join keys", ""]
        for j in joins:
            L.append(f"- `{j['column']}` → {', '.join('`'+t+'`' for t in j['tables'])}")
        L.append("")

    L += ["## Tables", ""]
    for t in profile["tables"]:
        rc = f"{t['row_count']:,}" if isinstance(t.get("row_count"), int) else "?"
        L.append(f"### `{t['schema']}.{t['table']}` — {rc} rows")
        if t.get("primary_key_guess"):
            L.append(f"_likely key: `{t['primary_key_guess']}`_")
        L.append("")
        L.append("| column | type | null % | ~distinct | flags |")
        L.append("|---|---|---|---|---|")
        for c in t.get("columns", []):
            flags = ", ".join(c.get("flags", []))
            L.append(f"| `{c['name']}` | {c['data_type']} | "
                     f"{c.get('null_pct', '?')} | {c.get('distinct_approx', '?')} | {flags} |")
        L.append("")
        if t.get("errors"):
            L.append("> errors: " + "; ".join(t["errors"]))
            L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Profile a Unity Catalog catalog.")
    ap.add_argument("--catalog", help="catalog to profile (default: workspace_config unity_catalog.catalog)")
    ap.add_argument("--schema", help="restrict to one schema (default: all)")
    ap.add_argument("--config", help="path to workspace_config.yml")
    ap.add_argument("--out", default="prep/out", help="output dir (default prep/out)")
    ap.add_argument("--max-tables", type=int, default=100)
    ap.add_argument("--max-agg-cols", type=int, default=40, help="columns per aggregate query")
    ap.add_argument("--top-k-cats", type=int, default=10)
    ap.add_argument("--sample-rows", type=int, default=3)
    ap.add_argument("--no-warehouse-start", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    catalog = args.catalog or cfg["catalog"]
    wh = cfg["warehouse_id"]
    if not catalog:
        ap.error("no catalog: pass --catalog or set unity_catalog.catalog / HACKATHON_CATALOG")
    if not wh:
        ap.error("no SQL warehouse: set compute.sql_warehouse_id / SQL_WAREHOUSE_ID")

    print(f"[profile] catalog={catalog} warehouse={wh} config={cfg['config_path']}")
    w = make_workspace_client(cfg)
    if not args.no_warehouse_start:
        print("[profile] warming warehouse…")
        ensure_warehouse_running(w, wh)

    tables = list_tables(w, wh, catalog, args.schema)[: args.max_tables]
    cols_by_table = list_columns(w, wh, catalog, args.schema)
    print(f"[profile] {len(tables)} tables")

    profiled = []
    for i, t in enumerate(tables, 1):
        key = (t["schema"], t["table"])
        cols = cols_by_table.get(key, [])
        print(f"[profile]   ({i}/{len(tables)}) {t['schema']}.{t['table']} — {len(cols)} cols")
        try:
            p = profile_table(w, wh, catalog, t["schema"], t["table"], cols,
                              max_agg_cols=args.max_agg_cols, top_k_cats=args.top_k_cats,
                              sample_rows=args.sample_rows)
            p["table_type"] = t.get("table_type")
            p["comment"] = t.get("comment")
            profiled.append(p)
        except Exception as e:  # keep going — one bad table shouldn't sink the run
            print(f"[profile]     ! {e}")
            profiled.append({"schema": t["schema"], "table": t["table"],
                             "errors": [str(e)], "columns": []})

    string_numeric = [
        {"table": f"{t['schema']}.{t['table']}", "column": c["name"],
         "numeric_string_ratio": c.get("numeric_string_ratio")}
        for t in profiled for c in t.get("columns", [])
        if "string-numeric (CAST to DOUBLE before aggregating)" in c.get("flags", [])
    ]
    profile = {
        "catalog": catalog,
        "schema_filter": args.schema,
        "warehouse_id": wh,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": profiled,
        "summary": {
            "table_count": len(profiled),
            "candidate_join_keys": find_join_keys(profiled),
            "string_numeric_columns": string_numeric,
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", catalog.lower()).strip("_")
    json_path = out_dir / f"profile_{slug}.json"
    md_path = out_dir / f"profile_{slug}.md"
    json_path.write_text(json.dumps(profile, indent=2, default=str))
    md_path.write_text(render_markdown(profile))
    print(f"[profile] wrote {json_path}")
    print(f"[profile] wrote {md_path}")
    print(f"[profile] next: python -m prep.graph_seed --profile {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

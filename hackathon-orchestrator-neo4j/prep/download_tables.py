#!/usr/bin/env python3
"""Download every table in a UC schema to local parquet (typed, via Arrow).

Day-of helper for the graph rebuild: pull the hackathon dataset locally so the
EDA / findings work (which feeds find_skill graph nodes) can run with pandas,
without a warehouse round-trip per cell.

Uses the Statement Execution API with EXTERNAL_LINKS + ARROW_STREAM (typed,
chunk-following, no inline 25 MiB cap), reusing the prep kit's warehouse warm-up.
Falls back to inline JSON (string-typed) if Arrow external links are unavailable.

Usage:
    python download_tables.py \
        --catalog databricks_virtue_foundation_dataset_dais_2026 \
        --schema virtue_foundation_dataset \
        --profile hackathon \
        --warehouse 7a84995ca3aefed0 \
        --out data/virtue_foundation
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ensure_warehouse_running, exec_sql, fq  # noqa: E402


def _client(profile: str):
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(profile=profile)


def list_tables(w, warehouse_id, catalog, schema) -> list[str]:
    cols, rows, _ = exec_sql(w, warehouse_id, f"SHOW TABLES IN {fq(catalog, schema)}")
    # SHOW TABLES → columns: database, tableName, isTemporary
    idx = cols.index("tableName") if "tableName" in cols else 1
    return [r[idx] for r in rows]


def _download_url(url: str) -> bytes:
    with urllib.request.urlopen(url) as resp:  # presigned, no auth header
        return resp.read()


def fetch_arrow(w, warehouse_id, catalog, schema, table) -> pa.Table:
    """SELECT * via EXTERNAL_LINKS + ARROW_STREAM, follow chunks, return a Table."""
    from databricks.sdk.service.sql import Disposition, Format

    stmt = f"SELECT * FROM {fq(catalog, schema, table)}"
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=stmt,
        disposition=Disposition.EXTERNAL_LINKS, format=Format.ARROW_STREAM,
        wait_timeout="0s",
    )
    import time
    sid = resp.statement_id
    deadline = time.time() + 600
    while True:
        state = resp.status.state.value if resp.status and resp.status.state else None
        if state in ("PENDING", "RUNNING"):
            if time.time() > deadline:
                raise RuntimeError(f"{table}: statement timed out")
            time.sleep(2.0)
            resp = w.statement_execution.get_statement(sid)
            continue
        break
    if resp.status.state.value != "SUCCEEDED":
        err = getattr(getattr(resp.status, "error", None), "message", "") or resp.status.state.value
        raise RuntimeError(f"{table}: {err}")

    batches: list[pa.RecordBatch] = []

    def _read_chunk(result) -> None:
        for link in (getattr(result, "external_links", None) or []):
            raw = _download_url(link.external_link)
            reader = ipc.open_stream(io.BytesIO(raw))
            batches.extend(reader)

    # Chunk 0 is resp.result. Prefer the manifest's authoritative chunk count;
    # for EXTERNAL_LINKS the per-chunk "next" pointer is unreliable, so iterate
    # explicitly over every chunk index rather than chasing next_chunk_index.
    manifest = getattr(resp, "manifest", None)
    total = getattr(manifest, "total_chunk_count", None) if manifest else None
    _read_chunk(resp.result)
    if total and total > 1:
        for i in range(1, total):
            _read_chunk(w.statement_execution.get_statement_result_chunk_n(sid, i))
    elif total is None:
        # Fallback: chase next_chunk_index off the link / result objects.
        nxt = None
        for link in (getattr(resp.result, "external_links", None) or []):
            nxt = getattr(link, "next_chunk_index", None) or nxt
        nxt = nxt or getattr(resp.result, "next_chunk_index", None)
        while nxt is not None:
            ch = w.statement_execution.get_statement_result_chunk_n(sid, nxt)
            _read_chunk(ch)
            nxt2 = getattr(ch, "next_chunk_index", None)
            for link in (getattr(ch, "external_links", None) or []):
                nxt2 = getattr(link, "next_chunk_index", None) or nxt2
            nxt = nxt2
    if not batches:
        # empty table — still need a schema; pull it cheaply
        cols, _, _ = exec_sql(w, warehouse_id, f"SELECT * FROM {fq(catalog, schema, table)} LIMIT 0")
        return pa.table({c: pa.array([], type=pa.string()) for c in cols})
    return pa.Table.from_batches(batches)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--profile", default="hackathon")
    ap.add_argument("--warehouse", required=True)
    ap.add_argument("--out", default="data")
    ap.add_argument("--tables", default="", help="comma-list; default = all in schema")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    w = _client(args.profile)
    print(f"warming warehouse {args.warehouse} (serverless cold start can take ~1-3 min)...", flush=True)
    ensure_warehouse_running(w, args.warehouse, wait_s=240)

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or \
        list_tables(w, args.warehouse, args.catalog, args.schema)
    print(f"tables in {args.catalog}.{args.schema}: {tables}\n", flush=True)

    summary = []
    for t in tables:
        print(f"→ {t}: fetching ...", flush=True)
        try:
            tbl = fetch_arrow(w, args.warehouse, args.catalog, args.schema, t)
        except Exception as e:
            print(f"  ARROW path failed ({e}); falling back to inline JSON", flush=True)
            cols, rows, trunc = exec_sql(
                w, args.warehouse, f"SELECT * FROM {fq(args.catalog, args.schema, t)}",
            )
            data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
            tbl = pa.table({c: pa.array(v, type=pa.string()) for c, v in data.items()})
            if trunc:
                print(f"  WARNING: inline result truncated for {t}", flush=True)
        dest = out / f"{t}.parquet"
        pq.write_table(tbl, dest)
        size_mb = dest.stat().st_size / 1e6
        print(f"  ✓ {tbl.num_rows:,} rows × {tbl.num_columns} cols → {dest} ({size_mb:.2f} MB)", flush=True)
        summary.append((t, tbl.num_rows, tbl.num_columns, round(size_mb, 2)))

    print("\n=== summary ===")
    for t, r, c, mb in summary:
        print(f"  {t:42s} {r:>10,} rows  {c:>3} cols  {mb:>7.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

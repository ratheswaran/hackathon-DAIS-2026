"""Apply the curated India Healthcare Access Genie-space config (idempotent).

The Genie space `01f168ec4bf01d27a00ac8069c1b06b8` is the orchestrator's PRIMARY
data-retrieval surface (`ask_genie_space`). A bare space (tables only, no
instructions) makes Genie blind-scan the messy Virtue Foundation tables — slow
and error-prone. This script pushes the curated `serialized_space`:

  * 1 text_instructions block  — the honesty contract, the PIN->district join
    spine, every CAST / normalization / DISTINCT-unique_id rule (sourced from the
    Aura find_skill graph's Rules + Columns).
  * 9 example_question_sqls     — certified, warehouse-VERIFIED runnable Q->SQL
    pairs (the join, zero-facility districts, care-lottery, worst-burden, ...).
  * 6 sample_questions          — UI chips.

Two non-obvious serialized-format gotchas (both cost a debug cycle):
  1. Every id-bearing array (`example_question_sqls`, `text_instructions`,
     `config.sample_questions`) MUST be sorted by `id` ascending, or the API
     rejects with "must be sorted by id".
  2. PIN extraction MUST use `try_cast(regexp_extract(...,'([0-9]{6})',1) AS INT)`,
     NOT plain CAST — regexp_extract returns '' on no-match and CAST('' AS INT)
     HARD-FAILS the whole Genie message (MessageStatus.FAILED). Likewise never
     filter `col <> '*'` on the DOUBLE-typed NFHS headline columns
     (all_w15_49_who_are_anaemic_pct, hh_member_covered_health_insurance_pct,
     institutional_birth_5y_pct) — that casts '*'->DOUBLE and fails; cast in a
     subquery and filter `IS NOT NULL` instead. The shipped serialized already
     obeys both; this note is so a future hand-edit doesn't regress them.

Usage:
    python apply.py                       # update the live space (profile=hackathon)
    PROFILE=hackathon SPACE_ID=... python apply.py
    python apply.py --verify              # also run every exemplar SQL on the warehouse
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient

HERE = Path(__file__).resolve().parent
SERIALIZED = HERE / "india_healthcare_access.serialized.json"

PROFILE = os.environ.get("PROFILE", "hackathon")
SPACE_ID = os.environ.get("SPACE_ID", "01f168ec4bf01d27a00ac8069c1b06b8")
WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", "7a84995ca3aefed0")


def _sorted_payload() -> str:
    s = json.loads(SERIALIZED.read_text())
    ins = s["instructions"]
    ins["example_question_sqls"] = sorted(ins["example_question_sqls"], key=lambda x: x["id"])
    ins["text_instructions"] = sorted(ins["text_instructions"], key=lambda x: x["id"])
    if s.get("config", {}).get("sample_questions"):
        s["config"]["sample_questions"] = sorted(s["config"]["sample_questions"], key=lambda x: x["id"])
    return json.dumps(s)


def main() -> None:
    w = WorkspaceClient(profile=PROFILE)
    ser = _sorted_payload()
    cur = w.api_client.do("GET", f"/api/2.0/genie/spaces/{SPACE_ID}?include_serialized_space=true")
    res = w.genie.update_space(SPACE_ID, serialized_space=ser, etag=cur.get("etag"))
    print(f"updated Genie space {res.space_id} | {res.title}")

    if "--verify" in sys.argv:
        from databricks.sdk.service.sql import StatementState
        s = json.loads(ser)
        ok = fail = 0
        for e in s["instructions"]["example_question_sqls"]:
            r = w.statement_execution.execute_statement(
                warehouse_id=WAREHOUSE_ID, statement=" ".join(e["sql"]), wait_timeout="50s")
            if r.status.state == StatementState.SUCCEEDED:
                ok += 1
            else:
                fail += 1
                print(f"  FAIL: {e['question'][0][:60]} :: "
                      f"{(r.status.error.message if r.status.error else '')[:100]}")
        print(f"exemplar verification: {ok} OK / {fail} FAIL")


if __name__ == "__main__":
    main()

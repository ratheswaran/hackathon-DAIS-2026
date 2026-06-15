"""Compare two eval runs:  python -m evals.compare baseline optimised"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"


def _load(label: str) -> dict:
    return json.loads((RUNS / f"{label}.json").read_text())


def _pct(a, b):
    if not a or b is None:
        return ""
    return f"{(b - a) / a * 100:+.1f}%"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python -m evals.compare <label_a> <label_b>")
    a, b = _load(sys.argv[1]), _load(sys.argv[2])
    bya = {r["id"]: r for r in a["results"]}
    byb = {r["id"]: r for r in b["results"]}

    print(f"| case | {a['label']} tok | {b['label']} tok | Δtok | "
          f"{a['label']} lat | {b['label']} lat | Δlat | pass a→b |")
    print("|---|---|---|---|---|---|---|---|")
    ta = tb = la = lb = 0
    for cid in bya:
        ra, rb = bya[cid], byb.get(cid)
        ma = ra["metrics"]
        if rb is None:
            print(f"| {cid} | {ma.get('total_tokens')} | — | | {ra['latency_s']} | — | | |")
            continue
        mb = rb["metrics"]
        ta += ma.get("total_tokens") or 0
        tb += mb.get("total_tokens") or 0
        la += ra["latency_s"]
        lb += rb["latency_s"]
        print(
            f"| {cid} | {ma.get('total_tokens')} | {mb.get('total_tokens')} "
            f"| {_pct(ma.get('total_tokens'), mb.get('total_tokens'))} "
            f"| {ra['latency_s']} | {rb['latency_s']} "
            f"| {_pct(ra['latency_s'], rb['latency_s'])} "
            f"| {'✓' if ra['grade']['pass'] else '✗'}→{'✓' if rb['grade']['pass'] else '✗'} |"
        )
    print(f"| **TOTAL** | {ta} | {tb} | {_pct(ta, tb)} | {round(la,1)} | {round(lb,1)} | {_pct(la, lb)} | |")


if __name__ == "__main__":
    main()

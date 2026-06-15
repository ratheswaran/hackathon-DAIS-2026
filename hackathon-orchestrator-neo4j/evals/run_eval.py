"""Eval suite runner.

Usage (from hackathon-orchestrator-neo4j/, with .venv-test):
    .venv-test/bin/python -m evals.run_eval --label baseline
    .venv-test/bin/python -m evals.run_eval --label fix-r1 --only edge-deck edge-infographic
    .venv-test/bin/python -m evals.run_eval --label quick --only ctl-routing --no-judge

Writes evals/runs/<label>.json (full per-call detail) and prints a summary
table. Compare runs with:  python -m evals.compare baseline fix-r1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from evals.harness import build_agent, load_env, run_case  # noqa: E402
from evals.graders import grade_case  # noqa: E402

RUNS_DIR = _HERE / "runs"


def fmt_row(cells, widths):
    return "| " + " | ".join(str(c).ljust(w) for c, w in zip(cells, widths)) + " |"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="run label, e.g. baseline")
    ap.add_argument("--cases", default=str(_HERE / "cases.yaml"))
    ap.add_argument("--only", nargs="*", help="case ids to run (default all)")
    ap.add_argument("--skip", nargs="*", default=[], help="case ids to skip")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--repeat", type=int, default=1, help="trials per case")
    args = ap.parse_args()

    cases = yaml.safe_load(Path(args.cases).read_text())
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    cases = [c for c in cases if c["id"] not in set(args.skip)]
    if not cases:
        sys.exit("no cases selected")

    print(f"== building agent (local, production wiring) ==", flush=True)
    graph, _orch = build_agent()

    judge_llm = None
    if not args.no_judge:
        from databricks_langchain import ChatDatabricks

        cfg = load_env()
        judge_llm = ChatDatabricks(
            endpoint=cfg.get("serving", {}).get("llm_endpoint_name", "gpt-5-external-provider")
        )

    results = []
    for case in cases:
        for trial in range(args.repeat):
            tag = f"{case['id']}" + (f"#{trial}" if args.repeat > 1 else "")
            print(f"\n=== {tag}: {case['turns'][0][:80]}…", flush=True)
            t0 = time.time()
            res = run_case(graph, case)
            res["trial"] = trial
            res["grade"] = grade_case(case, res, judge_llm)
            m = res["metrics"]
            status = "PASS" if res["grade"]["pass"] else "FAIL"
            soft = "" if res["grade"]["soft_pass"] else "  [over budget]"
            print(
                f"  {status}{soft}  {res['latency_s']}s · {m.get('llm_calls')} LLM calls · "
                f"{m.get('total_tokens')} tok (in {m.get('input_tokens')} / out {m.get('output_tokens')}) · "
                f"tools: {','.join(res['tool_sequence'][:12])}",
                flush=True,
            )
            for c in res["grade"]["checks"]:
                if not c["pass"]:
                    print(f"    ✗ {c['name']}{' (soft)' if not c['hard'] else ''}: {c['detail'][:160]}")
            results.append(res)

    # ---- summary ----
    RUNS_DIR.mkdir(exist_ok=True)
    out_path = RUNS_DIR / f"{args.label}.json"
    out_path.write_text(
        json.dumps(
            {"label": args.label, "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results},
            indent=2,
            default=str,
        )
    )

    headers = ["case", "pass", "lat_s", "llm", "in_tok", "out_tok", "total"]
    widths = [22, 4, 6, 4, 9, 8, 9]
    print("\n" + fmt_row(headers, widths))
    print(fmt_row(["-" * w for w in widths], widths))
    tot_in = tot_out = tot_lat = 0
    for r in results:
        m = r["metrics"]
        tot_in += m.get("input_tokens") or 0
        tot_out += m.get("output_tokens") or 0
        tot_lat += r["latency_s"]
        print(
            fmt_row(
                [
                    r["id"],
                    "✓" if r["grade"]["pass"] else "✗",
                    r["latency_s"],
                    m.get("llm_calls"),
                    m.get("input_tokens"),
                    m.get("output_tokens"),
                    m.get("total_tokens"),
                ],
                widths,
            )
        )
    print(fmt_row(["TOTAL", "", round(tot_lat, 1), "", tot_in, tot_out, tot_in + tot_out], widths))
    n_pass = sum(1 for r in results if r["grade"]["pass"])
    print(f"\n{n_pass}/{len(results)} passed · wrote {out_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""A/B token + latency comparison: file-walk orchestrator vs neo4j find_skill.

Sends the same probe queries to both serving endpoints, then reads each run's
MLflow trace and tabulates token usage (input/output/total/cache-read) and
wall-clock latency. Token usage is captured automatically by
``mlflow.langchain.autolog(log_traces=True)`` inside both agents — every trace
carries ``trace.info.token_usage`` aggregated across all LLM spans, so this
script only *reads* it; nothing is instrumented here.

Usage:
    .venv/bin/python ab_token_compare.py                  # all 5 probes, both variants
    .venv/bin/python ab_token_compare.py --variant neo4j  # one side only
    .venv/bin/python ab_token_compare.py --probe 0 2      # subset by index
    .venv/bin/python ab_token_compare.py --probes-file my_probes.json
    .venv/bin/python ab_token_compare.py --out results.json

Run it with any Python that has ``mlflow-skinny`` + ``requests`` (the
neo4j/hackathon-brain .venv works: it has both).
"""

import argparse
import configparser
import json
import sys
import time
from pathlib import Path

import requests

PROFILE = "hackathon-test"

VARIANTS = {
    "filewalk": {
        "endpoint": "agents_workspace-hackathon-orchestrator_agent_v3",
        "experiment": "/Shared/workspace.hackathon.orchestrator_agent_v3_traces",
    },
    "neo4j": {
        "endpoint": "agents_workspace-hackathon-orchestrator_agent_neo4j",
        "experiment": "/Shared/workspace.hackathon.orchestrator_agent_neo4j_traces",
    },
}

# One probe per route the graph has to win on: data, why, deck, infographic,
# new-knowledge. Swap via --probes-file if the handoff list differs.
DEFAULT_PROBES = [
    "What are an Afghan asylum seeker's chances of getting protection across "
    "EU countries? Which country is toughest?",
    "Why is asylum outcome called a lottery? Explain what drives the gap "
    "between Germany and Sweden for the same nationality.",
    "Build a 6-slide executive deck on the global displacement crisis.",
    "Create an infographic showing who really bears the refugee burden — "
    "wealth or geography?",
    "How many people are stuck waiting in the asylum backlog, and is it "
    "growing?",
]


def _databrickscfg(profile: str):
    cfg = configparser.ConfigParser()
    cfg.read(Path.home() / ".databrickscfg")
    host = cfg[profile]["host"].rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    return host, cfg[profile]["token"]


def query_endpoint(host, token, endpoint, prompt, conversation_id, timeout=900):
    url = f"{host}/serving-endpoints/{endpoint}/invocations"
    body = {
        "input": [{"role": "user", "content": prompt}],
        "context": {"conversation_id": conversation_id},
    }
    t0 = time.time()
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=timeout,
    )
    elapsed = time.time() - t0
    resp.raise_for_status()
    return resp.json(), elapsed


def newest_trace_after(client, exp_id, t0_ms, retries=10, wait_s=15):
    """Traces are logged async after the response returns — poll briefly."""
    for _ in range(retries):
        traces = client.search_traces(locations=[exp_id], max_results=5)
        for t in traces:
            if t.info.request_time and t.info.request_time >= t0_ms:
                return t
        time.sleep(wait_s)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(VARIANTS), action="append",
                    help="run only this variant (repeatable); default both")
    ap.add_argument("--probe", type=int, nargs="*",
                    help="probe indices to run; default all")
    ap.add_argument("--probes-file", help="JSON file with a list of probe strings")
    ap.add_argument("--out", help="write results JSON here")
    args = ap.parse_args()

    probes = DEFAULT_PROBES
    if args.probes_file:
        probes = json.loads(Path(args.probes_file).read_text())
    idxs = args.probe if args.probe else range(len(probes))
    variants = args.variant or list(VARIANTS)

    host, token = _databrickscfg(PROFILE)

    import mlflow
    from mlflow import MlflowClient
    mlflow.set_tracking_uri("databricks")
    client = MlflowClient()
    exp_ids = {}
    for v in variants:
        exp = client.get_experiment_by_name(VARIANTS[v]["experiment"])
        if exp is None:
            sys.exit(f"experiment not found for {v}: {VARIANTS[v]['experiment']}")
        exp_ids[v] = exp.experiment_id

    results = []
    for i in idxs:
        prompt = probes[i]
        for v in variants:
            label = f"probe{i}/{v}"
            print(f"\n=== {label}: {prompt[:70]}…")
            t0_ms = int(time.time() * 1000)
            try:
                _, elapsed = query_endpoint(
                    host, token, VARIANTS[v]["endpoint"], prompt,
                    conversation_id=f"ab-{v}-p{i}-{t0_ms}",
                )
            except Exception as e:
                print(f"  QUERY FAILED: {e}")
                results.append({"probe": i, "variant": v, "error": str(e)})
                continue
            trace = newest_trace_after(client, exp_ids[v], t0_ms)
            usage = (trace.info.token_usage or {}) if trace else {}
            row = {
                "probe": i,
                "variant": v,
                "latency_s": round(elapsed, 1),
                "trace_id": trace.info.trace_id if trace else None,
                **{k: usage.get(k) for k in (
                    "input_tokens", "output_tokens", "total_tokens",
                    "cache_read_input_tokens")},
            }
            print(f"  {row}")
            results.append(row)

    print("\n\n| probe | variant | latency_s | input_tok | output_tok | total_tok | cache_read |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        if "error" in r:
            print(f"| {r['probe']} | {r['variant']} | ERROR: {r['error'][:60]} | | | | |")
        else:
            print(f"| {r['probe']} | {r['variant']} | {r['latency_s']} "
                  f"| {r.get('input_tokens')} | {r.get('output_tokens')} "
                  f"| {r.get('total_tokens')} | {r.get('cache_read_input_tokens')} |")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"probes": list(probes), "results": results}, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    import os
    os.environ.setdefault("DATABRICKS_CONFIG_PROFILE", PROFILE)
    main()

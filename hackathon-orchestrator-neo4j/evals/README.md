# Eval suite — latency & token optimisation harness

Methodology after Anthropic's *Prompting Playbook* (Code with Claude, Margo
van Laar): a representative eval of **control / edge / capability-boundary**
cases, run V0 to surface failure modes, then target them **one at a time** —
prompt hygiene first, tools-over-instructions, harness changes — re-running
the suite after every change so improvements are measured, not vibed.

## What it measures

Per case: wall-clock latency, **per-LLM-call input/output tokens** (the loop's
compounding cost), LLM call count, tool sequence + per-tool latency + result
size, pass/fail against hard graders (tool contracts, artifact links, Genie
space routing) and an LLM judge (answer quality vs rubric). Budgets
(tokens/latency/calls) are soft checks — they're the optimisation metric.

## How it runs

`harness.py` imports `deploy_orchestrator_agent` and calls
`create_production_agent()` **locally**: same prompts, tool factories,
middleware, subagents, real Lakebase variable store, live Neo4j find_skill,
live Genie, live gpt-5.5. Only the checkpointer/memory-store are in-memory.
What the model sees is byte-identical to serving — token numbers transfer.
No redeploy needed between iterations: edit source → re-run → compare.

```bash
# from hackathon-orchestrator-neo4j/
.venv-test/bin/python -m evals.run_eval --label baseline           # full suite
.venv-test/bin/python -m evals.run_eval --label r1 --only edge-deck
.venv-test/bin/python -m evals.compare baseline r1                 # delta table
```

Final verification of a winning variant happens on the deployed endpoint via
`ab_token_compare.py` (MLflow trace token usage), which this suite complements
but does not replace.

## Files

- `cases.yaml` — 12 cases: 3 control, 6 edge (the 5 A/B probes + vague-query),
  2 boundary (out-of-scope decline, data-coverage honesty), 1 multi-turn.
- `harness.py` — local production-agent build + MetricsCallback.
- `graders.py` — programmatic checks + LLM judge (gpt-5.5).
- `run_eval.py` / `compare.py` — runner + run-to-run diff.
- `runs/` — saved run JSONs (full per-call detail).

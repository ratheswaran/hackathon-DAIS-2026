"""Graders: programmatic checks (hard) + LLM judge (hard) + budgets (soft).

Per the Prompting Playbook split: where a rule is *hard* (tool sequence,
artifact link, genie space id) we check it in Python; where it is *soft*
(answer quality, methodology) an LLM judge grades against a rubric. Token /
latency budgets are reported as soft checks — they are the optimisation
metric, not a correctness gate, until a baseline freezes them as regression
thresholds.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

URL_RE = re.compile(r"https?://[^\s)\]>\"']+")

JUDGE_SYSTEM = (
    "You are a strict eval judge for a refugee-data analytics agent. "
    "Grade the agent's final answer against the rubric. Judge ONLY what the "
    "rubric asks — not style. Reply with EXACTLY one JSON object: "
    '{"pass": true|false, "reason": "<one sentence>"}'
)


def _check(name: str, ok: bool, detail: str = "", hard: bool = True) -> dict:
    return {"name": name, "pass": bool(ok), "detail": detail, "hard": hard}


def _genie_space_ids(result: dict) -> list[str]:
    ids = []
    for tc in result.get("orchestrator_tool_calls", []):
        if tc.get("name") == "ask_genie_space":
            m = re.search(r"01f[0-9a-f]+", tc.get("args", ""))
            if m:
                ids.append(m.group(0))
    return ids


def judge_answer(rubric: str, case: dict, result: dict, llm) -> dict:
    convo = "\n\n".join(
        f"USER: {t['user']}\nAGENT: {t['answer'] or '(no answer)'}"
        for t in result["turns"]
    )
    prompt = (
        f"RUBRIC:\n{rubric.strip()}\n\nCONVERSATION TO GRADE:\n{convo[:24000]}"
    )
    try:
        resp = llm.invoke(
            [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}]
        )
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        verdict = json.loads(m.group(0)) if m else {"pass": False, "reason": "unparseable judge output"}
    except Exception as e:  # noqa: BLE001
        verdict = {"pass": False, "reason": f"judge error: {e}"}
    return verdict


def grade_case(case: dict, result: dict, judge_llm: Optional[Any]) -> dict:
    g = case.get("graders", {}) or {}
    checks: list[dict] = []

    if result.get("error"):
        checks.append(_check("no_run_error", False, result["error"]))
    else:
        checks.append(_check("no_run_error", True))

    seq = result.get("tool_sequence", [])
    answer_text = " ".join(t.get("answer") or "" for t in result.get("turns", []))

    for t in g.get("must_call", []) or []:
        checks.append(_check(f"must_call:{t}", t in seq, f"sequence={seq[:20]}"))
    for t in g.get("must_not_call", []) or []:
        checks.append(_check(f"must_not_call:{t}", t not in seq, f"sequence={seq[:20]}"))

    if g.get("genie_space_prefix"):
        ids = _genie_space_ids(result)
        ok = any(i.startswith(g["genie_space_prefix"]) for i in ids)
        # ask_genie_space may resolve the space internally; only fail if a
        # DIFFERENT space was used. No ids observed → not graded hard.
        if ids:
            checks.append(_check("genie_space", ok, f"ids={ids}"))

    if g.get("max_genie_calls") is not None:
        n = seq.count("ask_genie_space")
        checks.append(_check("max_genie_calls", n <= g["max_genie_calls"], f"n={n}"))

    if g.get("expect_url"):
        checks.append(
            _check("artifact_url", bool(URL_RE.search(answer_text)), "no URL in final answer")
        )

    # Artifact-by-tool: the app auto-opens compose_* artifacts from the tool
    # JSON, and the prompt FORBIDS pasting infographic links — so the correct
    # check is "the named tool ran and returned ok", not URL-in-answer.
    if g.get("expect_artifact_tool"):
        name = g["expect_artifact_tool"]
        ok = any(
            t.get("name") == name
            and not t.get("error")
            and '"status": "ok"' in (t.get("output_head") or "").replace('": "', '": "')
            for t in result.get("tool_calls_detail", [])
        ) or any(
            t.get("name") == name and not t.get("error") and "ok" in (t.get("output_head") or "")[:60]
            for t in result.get("tool_calls_detail", [])
        )
        checks.append(_check(f"artifact_tool:{name}", ok, "no successful call observed"))

    # tool-error scan: any tool result that errored (hard — failures burn
    # tokens AND signal a broken contract)
    tool_errors = [t for t in result.get("tool_calls_detail", []) if t.get("error")]
    checks.append(
        _check(
            "no_tool_errors",
            not tool_errors,
            "; ".join(f"{t['name']}: {t['error'][:80]}" for t in tool_errors[:3]),
        )
    )

    # LLM judge
    if g.get("judge") and judge_llm is not None:
        verdict = judge_answer(g["judge"], case, result, judge_llm)
        checks.append(_check("judge", verdict.get("pass", False), verdict.get("reason", "")))

    # budgets — soft
    b = g.get("budgets", {}) or {}
    m = result.get("metrics", {})
    if b.get("total_tokens") and m.get("total_tokens"):
        checks.append(
            _check(
                "budget:total_tokens",
                m["total_tokens"] <= b["total_tokens"],
                f"{m['total_tokens']} vs {b['total_tokens']}",
                hard=False,
            )
        )
    if b.get("latency_s"):
        checks.append(
            _check(
                "budget:latency_s",
                result["latency_s"] <= b["latency_s"],
                f"{result['latency_s']} vs {b['latency_s']}",
                hard=False,
            )
        )
    if b.get("llm_calls") and m.get("llm_calls"):
        checks.append(
            _check(
                "budget:llm_calls",
                m["llm_calls"] <= b["llm_calls"],
                f"{m['llm_calls']} vs {b['llm_calls']}",
                hard=False,
            )
        )

    hard_pass = all(c["pass"] for c in checks if c["hard"])
    soft_pass = all(c["pass"] for c in checks if not c["hard"])
    return {"pass": hard_pass, "soft_pass": soft_pass, "checks": checks}

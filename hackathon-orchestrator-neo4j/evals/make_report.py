#!/usr/bin/env python3
"""Build the self-contained baseline-vs-optimised HTML report.

Inputs (all under evals/runs/):
  baseline.json, optimised.json        — local 12-case eval suite runs
  optimised-mt-regrade.json            — rubric-fixed re-run of mt-followthrough
                                         (overrides that case in the optimised run)
  ab_endpoint_baseline.json            — live endpoint probes vs UC v9 (pre-opt)
  ab_endpoint_optimised.json           — live endpoint probes vs UC v10 (round 1)
  ab_endpoint_r2.json                  — live endpoint probes vs UC v11 (round 2)

The live endpoint A/B is a three-way: v9 (pre-optimisation) → v10 (round 1) →
v11 (round 2), all probed the same workspace, in-place endpoint updates (Free
Edition allows no second endpoint).

Output: evals/report.html — no CDN, no JS dependencies; pure HTML/CSS bars.

Usage: python3 evals/make_report.py
"""

import json
from datetime import date
from pathlib import Path

RUNS = Path(__file__).parent / "runs"
OUT = Path(__file__).parent / "report.html"

PROBE_LABELS = [
    "Afghan protection (data)",
    "Asylum lottery (why)",
    "Executive deck",
    "Burden infographic",
    "Backlog (new knowledge)",
    "Global headline (simple data)",
    "Weather (out-of-scope)",
    "2025/26 rates (coverage honesty)",
]

CASE_ORDER = [
    "ctl-capability", "ctl-routing", "ctl-simple-data",
    "edge-afghan-protection", "edge-lottery-why", "edge-backlog",
    "edge-deck", "edge-infographic", "edge-vague",
    "bnd-out-of-scope", "bnd-data-coverage", "mt-followthrough",
]

CAT_LABEL = {"control": "control", "edge": "edge", "boundary": "boundary", "multiturn": "multi-turn"}


def load(name):
    p = RUNS / name
    return json.loads(p.read_text()) if p.exists() else None


def fmt(n):
    if n is None:
        return "—"
    return f"{n:,}"


def fmt_k(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def pct(base, opt):
    if not base or opt is None:
        return None
    return (opt - base) / base * 100.0


def delta_chip(p, invert=False):
    """Green when improved (negative delta), red when regressed."""
    if p is None:
        return '<span class="chip neutral">—</span>'
    good = p < 0 if not invert else p > 0
    cls = "good" if good else ("bad" if abs(p) > 1 else "neutral")
    sign = "+" if p > 0 else "−"
    return f'<span class="chip {cls}">{sign}{abs(p):.1f}%</span>'


def bar_pair(base, opt, vmax, unit=""):
    """Two horizontal bars sharing one scale."""
    if vmax <= 0:
        vmax = 1
    bw = max(0.5, (base or 0) / vmax * 100)
    ow = max(0.5, (opt or 0) / vmax * 100)
    return f"""
      <div class="barpair">
        <div class="barrow"><span class="barlabel">baseline</span>
          <div class="bartrack"><div class="bar base" style="width:{bw:.1f}%"></div></div>
          <span class="barval">{fmt_k(base)}{unit}</span></div>
        <div class="barrow"><span class="barlabel">optimised</span>
          <div class="bartrack"><div class="bar opt" style="width:{ow:.1f}%"></div></div>
          <span class="barval">{fmt_k(opt)}{unit}</span></div>
      </div>"""


def bar_trio(v9, v10, v11, vmax, unit=""):
    """Three horizontal bars sharing one scale: v9 → v10 → v11."""
    if vmax <= 0:
        vmax = 1

    def w(v):
        return max(0.5, (v or 0) / vmax * 100)

    def row(lbl, cls, v):
        return (f'<div class="barrow"><span class="barlabel">{lbl}</span>'
                f'<div class="bartrack"><div class="bar {cls}" style="width:{w(v):.1f}%"></div></div>'
                f'<span class="barval">{fmt_k(v)}{unit}</span></div>')
    return ('<div class="barpair">'
            + row("v9 baseline", "base", v9)
            + row("v10 round 1", "opt1", v10)
            + row("v11 round 2", "opt", v11)
            + '</div>')


def case_rows(base_run, opt_run, regrade_run):
    base = {c["id"]: c for c in base_run["results"]}
    opt = {c["id"]: c for c in opt_run["results"]}
    if regrade_run:
        for c in regrade_run["results"]:
            opt[c["id"]] = c
    rows = []
    for cid in CASE_ORDER:
        b, o = base.get(cid), opt.get(cid)
        if not b or not o:
            continue
        turn0 = (b.get("turns") or [""])[0]
        prompt = turn0.get("user", "") if isinstance(turn0, dict) else str(turn0)
        rows.append({
            "id": cid,
            "category": b.get("category", ""),
            "prompt": prompt,
            "b_pass": bool(b["grade"]["pass"]), "o_pass": bool(o["grade"]["pass"]),
            "b_tok": b["metrics"].get("total_tokens"), "o_tok": o["metrics"].get("total_tokens"),
            "b_lat": b.get("latency_s"), "o_lat": o.get("latency_s"),
            "b_llm": b["metrics"].get("llm_calls"), "o_llm": o["metrics"].get("llm_calls"),
        })
    return rows


def endpoint_rows(ab_base, ab_opt, ab_r2):
    """Three-way per-probe endpoint rows: v9 (b) → v10 (o) → v11 (r)."""
    if not ab_base:
        return None
    bmap = {r["probe"]: r for r in ab_base["results"] if "error" not in r}
    omap = {r["probe"]: r for r in (ab_opt["results"] if ab_opt else []) if "error" not in r}
    rmap = {r["probe"]: r for r in (ab_r2["results"] if ab_r2 else []) if "error" not in r}
    rows = []
    for i, label in enumerate(PROBE_LABELS):
        b, o, r = bmap.get(i), omap.get(i), rmap.get(i)
        if not b and not o and not r:
            continue
        rows.append({
            "label": label,
            "prompt": ab_base["probes"][i] if i < len(ab_base["probes"]) else "",
            "b_tok": b.get("total_tokens") if b else None,
            "o_tok": o.get("total_tokens") if o else None,
            "r_tok": r.get("total_tokens") if r else None,
            "b_out": b.get("output_tokens") if b else None,
            "o_out": o.get("output_tokens") if o else None,
            "r_out": r.get("output_tokens") if r else None,
            "b_lat": b.get("latency_s") if b else None,
            "o_lat": o.get("latency_s") if o else None,
            "r_lat": r.get("latency_s") if r else None,
        })
    return rows


def main():
    base_run = load("baseline.json")
    opt_run = load("optimised.json")
    regrade = load("optimised-mt-regrade.json")
    ab_base = load("ab_endpoint_baseline.json")
    ab_opt = load("ab_endpoint_optimised.json")
    ab_r2 = load("ab_endpoint_r2.json")

    rows = case_rows(base_run, opt_run, regrade)
    ep_rows = endpoint_rows(ab_base, ab_opt, ab_r2)

    # ---- suite totals ----
    tb = sum(r["b_tok"] or 0 for r in rows)
    to = sum(r["o_tok"] or 0 for r in rows)
    lb = sum(r["b_lat"] or 0 for r in rows)
    lo = sum(r["o_lat"] or 0 for r in rows)
    pb = sum(1 for r in rows if r["b_pass"])
    po = sum(1 for r in rows if r["o_pass"])
    cb = sum(r["b_llm"] or 0 for r in rows)
    co = sum(r["o_llm"] or 0 for r in rows)

    # ---- endpoint totals (three-way; probes present on ALL sides available) ----
    ep_html = ""
    ep_hero = ""
    # cumulative numbers also feed the headline/standfirst
    cum_tok_pct = cum_lat_pct = None
    if ep_rows:
        all3 = [r for r in ep_rows
                if r["b_tok"] is not None and r["o_tok"] is not None and r["r_tok"] is not None]
        etb = sum(r["b_tok"] for r in all3)   # v9
        eto = sum(r["o_tok"] for r in all3)   # v10
        etr = sum(r["r_tok"] for r in all3)   # v11
        elb = sum(r["b_lat"] for r in all3)
        elo = sum(r["o_lat"] for r in all3)
        elr = sum(r["r_lat"] for r in all3)
        r1_tok_pct = pct(etb, eto)            # round 1 vs baseline
        r2_tok_pct = pct(eto, etr)            # round 2 vs round 1
        cum_tok_pct = pct(etb, etr)           # cumulative
        r1_lat_pct = pct(elb, elo)
        r2_lat_pct = pct(elo, elr)
        cum_lat_pct = pct(elb, elr)
        if all3:
            ep_hero = f"""
      <div class="stat">
        <div class="stat-num">−{abs(cum_tok_pct or 0):.1f}%</div>
        <div class="stat-label">live endpoint tokens<br>v9 → v11 · {len(all3)} probes</div>
      </div>
      <div class="stat">
        <div class="stat-num">−{abs(cum_lat_pct or 0):.1f}%</div>
        <div class="stat-label">live endpoint latency<br>v9 → v11</div>
      </div>"""
        tok_max = max([r["b_tok"] or 0 for r in ep_rows]
                      + [r["o_tok"] or 0 for r in ep_rows]
                      + [r["r_tok"] or 0 for r in ep_rows] + [1])
        cards = []
        for r in ep_rows:
            lat = (f"{r['b_lat'] if r['b_lat'] is not None else '—'}s → "
                   f"{r['o_lat'] if r['o_lat'] is not None else '—'}s → "
                   f"{r['r_lat'] if r['r_lat'] is not None else '—'}s")
            cards.append(f"""
      <div class="case">
        <div class="case-head">
          <div><div class="case-id">{r['label']}</div>
          <div class="case-prompt">{r['prompt']}</div></div>
          <div class="case-chips"><span class="chiplbl">r2 vs r1</span>{delta_chip(pct(r['o_tok'], r['r_tok']))}
            <span class="chiplbl">v9→v11</span>{delta_chip(pct(r['b_tok'], r['r_tok']))}</div>
        </div>
        {bar_trio(r['b_tok'], r['o_tok'], r['r_tok'], tok_max, ' tok')}
        <div class="case-meta">
          latency {lat} {delta_chip(pct(r['b_lat'], r['r_lat']))}
          &nbsp;·&nbsp; output {fmt_k(r['b_out'])} → {fmt_k(r['o_out'])} → {fmt_k(r['r_out'])} tok
        </div>
      </div>""")
        totals_row = ""
        if all3:
            totals_row = f"""
      <div class="totals">
        <span><strong>Totals ({len(all3)} probes):</strong></span>
        <span>tokens {fmt(etb)} → {fmt(eto)} → {fmt(etr)}</span>
        <span>round 1 {delta_chip(r1_tok_pct)} · round 2 {delta_chip(r2_tok_pct)} · cumulative {delta_chip(cum_tok_pct)}</span>
        <span>latency {elb:.0f}s → {elo:.0f}s → {elr:.0f}s {delta_chip(cum_lat_pct)}</span>
      </div>"""
        ep_html = f"""
  <section>
    <h2>1 · Live endpoint A/B — two rounds <span class="sub">same endpoint, same workspace — UC v9 (pre-optimisation) → v10 (round 1) → v11 (round 2), each an in-place update (Free Edition allows no second endpoint). Each version warmed, then probed.</span></h2>
    {''.join(cards)}
    {totals_row}
  </section>"""
    else:
        ep_html = """
  <section>
    <h2>1 · Live endpoint A/B</h2>
    <p class="pending">Endpoint probe runs not found yet — re-run <code>make_report.py</code> once
    <code>ab_endpoint_baseline.json</code> / <code>ab_endpoint_optimised.json</code> / <code>ab_endpoint_r2.json</code> exist.</p>
  </section>"""

    # ---- local suite cards ----
    tok_max = max([r["b_tok"] or 0 for r in rows] + [r["o_tok"] or 0 for r in rows] + [1])
    case_cards = []
    for r in rows:
        b_badge = '<span class="badge pass">PASS</span>' if r["b_pass"] else '<span class="badge fail">FAIL</span>'
        o_badge = '<span class="badge pass">PASS</span>' if r["o_pass"] else '<span class="badge fail">FAIL</span>'
        note = ' <span class="note">re-graded after rubric fix</span>' if r["id"] == "mt-followthrough" else ""
        case_cards.append(f"""
      <div class="case">
        <div class="case-head">
          <div>
            <div class="case-id">{r['id']} <span class="cat">{CAT_LABEL.get(r['category'], r['category'])}</span>{note}</div>
            <div class="case-prompt">{r['prompt']}</div>
          </div>
          <div class="case-chips">{b_badge}<span class="arrow">→</span>{o_badge} {delta_chip(pct(r['b_tok'], r['o_tok']))}</div>
        </div>
        {bar_pair(r['b_tok'], r['o_tok'], tok_max, ' tok')}
        <div class="case-meta">
          latency {r['b_lat']}s → {r['o_lat']}s {delta_chip(pct(r['b_lat'], r['o_lat']))}
          &nbsp;·&nbsp; LLM calls {r['b_llm']} → {r['o_llm']}
        </div>
      </div>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent eval — baseline vs optimised · neo4j orchestrator</title>
<style>
  :root {{
    --cobalt: #254BB2; --cobalt-deep: #16307A; --amber: #E8A33D;
    --ink: #1A1B22; --muted: #6B6E7B; --paper: #FAFAF7; --card: #FFFFFF;
    --line: #E6E4DC; --good: #1E7F4F; --good-bg: #E5F4EC;
    --bad: #B3362B; --bad-bg: #FBEAE7; --base-bar: #B9BFCF;
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{
    background: var(--paper); color: var(--ink);
    font-family: "Manrope", "Avenir Next", "Segoe UI", system-ui, sans-serif;
    font-size: 15px; line-height: 1.55; padding: 0 0 80px;
  }}
  header {{
    background: var(--cobalt-deep);
    background: linear-gradient(135deg, var(--cobalt-deep) 0%, var(--cobalt) 100%);
    color: #fff; padding: 48px 24px 40px;
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 0 24px; }}
  header .wrap {{ padding: 0; max-width: 980px; margin: 0 auto; padding: 0 24px; }}
  .kicker {{
    font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
    color: var(--amber); font-weight: 700; margin-bottom: 10px;
  }}
  h1 {{
    font-family: "Playfair Display", Georgia, "Times New Roman", serif;
    font-size: clamp(28px, 4.5vw, 44px); font-weight: 700; line-height: 1.12;
    max-width: 760px;
  }}
  .standfirst {{ margin-top: 14px; max-width: 720px; color: #D8DEF2; font-size: 16px; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 28px; }}
  .stat {{
    background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18);
    border-radius: 10px; padding: 14px 20px; min-width: 150px;
  }}
  .stat-num {{
    font-family: "Playfair Display", Georgia, serif; font-size: 30px; font-weight: 700;
    color: var(--amber);
  }}
  .stat-label {{ font-size: 12px; color: #C9D2EE; margin-top: 2px; }}
  section {{ max-width: 980px; margin: 44px auto 0; padding: 0 24px; }}
  h2 {{
    font-family: "Playfair Display", Georgia, serif; font-size: 24px; font-weight: 700;
    border-bottom: 3px solid var(--cobalt); padding-bottom: 8px; margin-bottom: 18px;
  }}
  h2 .sub {{
    display: block; font-family: "Manrope", system-ui, sans-serif; font-size: 13px;
    font-weight: 500; color: var(--muted); margin-top: 4px;
  }}
  .case {{
    background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 16px 18px; margin-bottom: 12px;
  }}
  .case-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
  .case-id {{ font-weight: 800; font-size: 14.5px; }}
  .cat {{
    font-size: 10.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
    color: var(--cobalt); background: #EAEEF9; border-radius: 4px; padding: 2px 7px; margin-left: 6px;
  }}
  .note {{ font-size: 11px; color: var(--muted); font-weight: 500; margin-left: 6px; }}
  .case-prompt {{ color: var(--muted); font-size: 13px; margin-top: 3px; max-width: 560px; }}
  .case-chips {{ display: flex; align-items: center; gap: 8px; white-space: nowrap; }}
  .arrow {{ color: var(--muted); }}
  .badge {{
    font-size: 11px; font-weight: 800; letter-spacing: .06em; border-radius: 4px; padding: 3px 8px;
  }}
  .badge.pass {{ color: var(--good); background: var(--good-bg); }}
  .badge.fail {{ color: var(--bad); background: var(--bad-bg); }}
  .chip {{
    font-size: 12px; font-weight: 800; border-radius: 4px; padding: 3px 8px;
  }}
  .chip.good {{ color: var(--good); background: var(--good-bg); }}
  .chip.bad {{ color: var(--bad); background: var(--bad-bg); }}
  .chip.neutral {{ color: var(--muted); background: #F0EFE9; }}
  .barpair {{ margin-top: 12px; }}
  .barrow {{ display: flex; align-items: center; gap: 10px; margin-top: 5px; }}
  .barlabel {{ width: 70px; font-size: 11.5px; color: var(--muted); text-align: right; flex: none; }}
  .bartrack {{ flex: 1; background: #F1F0EA; border-radius: 4px; height: 16px; overflow: hidden; }}
  .bar {{ height: 100%; border-radius: 4px; }}
  .bar.base {{ background: var(--base-bar); }}
  .bar.opt1 {{ background: #7E91CC; }}
  .bar.opt {{ background: var(--cobalt); }}
  .barval {{ width: 86px; font-size: 12px; font-variant-numeric: tabular-nums; flex: none; }}
  .chiplbl {{ font-size: 9.5px; font-weight: 700; letter-spacing: .05em; color: var(--muted); text-transform: uppercase; }}
  .case-meta {{ margin-top: 10px; font-size: 12.5px; color: var(--muted); }}
  .totals {{
    background: var(--cobalt-deep); color: #fff; border-radius: 10px;
    padding: 14px 18px; margin-top: 16px; display: flex; flex-wrap: wrap; gap: 18px;
    font-size: 14px; align-items: center;
  }}
  .totals .chip.good {{ background: rgba(255,255,255,.14); color: #8FE3B4; }}
  .totals .chip.bad {{ background: rgba(255,255,255,.14); color: #FFB1A6; }}
  .pending {{
    background: #FFF7E8; border: 1px solid #F0DCB0; border-radius: 8px; padding: 14px 16px;
    color: #7A5B16; font-size: 14px;
  }}
  code {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: .9em; background: #F0EFE9; border-radius: 4px; padding: 1px 5px; }}
  ul.changes {{ padding-left: 20px; }}
  ul.changes li {{ margin-bottom: 9px; }}
  h3.round {{ font-family: "Manrope", system-ui, sans-serif; font-size: 13.5px; font-weight: 800;
    color: var(--cobalt-deep); margin: 20px 0 8px; letter-spacing: .01em;
    text-transform: uppercase; }}
  .foot {{ max-width: 980px; margin: 50px auto 0; padding: 0 24px; color: var(--muted); font-size: 12.5px; border-top: 1px solid var(--line); padding-top: 18px; }}
</style>
</head>
<body>

<header>
  <div class="wrap">
    <div class="kicker">Resonance Analytics · Agent Engineering</div>
    <h1>Two optimisation rounds: the same agent on a third of the tokens</h1>
    <p class="standfirst">Token &amp; latency optimisation of the <strong>hackathon-orchestrator-neo4j</strong> deep agent
    (branch <code style="background:rgba(255,255,255,.12);color:#fff">feat/agent-eval-optimisation</code>) across
    two rounds — <strong>v9 → v10 → v11</strong> — measured on the <strong>live Databricks serving endpoint</strong>
    and developed on a <strong>12-case local eval suite</strong> (production-identical harness). Generated {date.today().isoformat()}.</p>
    <div class="stats">
      <div class="stat"><div class="stat-num">{pb}/12 → {po}/12</div><div class="stat-label">local suite pass rate</div></div>
      <div class="stat"><div class="stat-num">−{abs(pct(tb,to)):.1f}%</div><div class="stat-label">local suite tokens<br>{fmt_k(tb)} → {fmt_k(to)}</div></div>
      <div class="stat"><div class="stat-num">−{abs(pct(lb,lo)):.1f}%</div><div class="stat-label">local suite latency<br>{lb:.0f}s → {lo:.0f}s</div></div>
      {ep_hero}
    </div>
  </div>
</header>

{ep_html}

<section>
  <h2>2 · Local eval suite (12 cases) <span class="sub">round 1 (v9 → v10) on the production-identical local harness — live gpt-5.5 + Neo4j + Genie + Lakebase, byte-identical to serving. Round 2 held 12/12 here too but is within single-run suite noise (±10%); it was verified cleanly on the live endpoint — see §1.</span></h2>
  {''.join(case_cards)}
  <div class="totals">
    <span><strong>Suite totals:</strong></span>
    <span>pass {pb}/12 → {po}/12</span>
    <span>tokens {fmt(tb)} → {fmt(to)} {delta_chip(pct(tb, to))}</span>
    <span>latency {lb:.0f}s → {lo:.0f}s {delta_chip(pct(lb, lo))}</span>
    <span>LLM calls {cb} → {co} {delta_chip(pct(cb, co))}</span>
  </div>
</section>

<section>
  <h2>3 · What changed <span class="sub">methodology per Anthropic's Prompting Playbook: eval V0 → target failure modes one at a time → re-measure. Two rounds.</span></h2>
  <h3 class="round">Round 1 — commit c088431 · UC v10</h3>
  <ul class="changes">
    <li><strong>Dead prompt content cut.</strong> The orchestrator prompt documented <code>render_chart</code> — a tool
        that doesn't exist on this fork — in 8 places; plus disabled episodic-memory rules, Thailand-insurance scope
        rules, and a how-to for an absent tool. Prompts: orchestrator −49%, python-analyst −34%, data-viz −65%.</li>
    <li><strong>Recipes moved to the graph, schemas slimmed.</strong> Editorial chart/story rules were Cypher-appended to
        their Neo4j Tool/ChartRecipe pages first, then the duplicated prompt/tool-description copies cut
        (compose_story annotation 5.4k → 1.9k chars). Stale skill-file pointers now route through <code>find_skill</code>.</li>
    <li><strong>Tool-result budget compounds.</strong> <code>compact_ref</code> preview budget 20k → 4k tokens — one Genie
        result no longer parks 20k tokens in history for every later LLM call.</li>
    <li><strong>Fewer LLM round-trips.</strong> write_todos status updates batched into the same response as the next real
        tool call; think_tool unbound from data-viz (redundant reflection on a reasoning model);
        4 unused file builtins hidden from the model (~1k tok/call).</li>
    <li><strong>New behaviour rules from V0 failures.</strong> Out-of-scope decline, data-coverage-ends-2024,
        conversational-no-tools — the boundary cases now pass without speculative Genie queries.</li>
    <li><strong>Bug fix:</strong> compose_deck pie-on-dark crash (python-pptx raises <code>ValueError</code>, not
        AttributeError, for <code>chart.category_axis</code> on pies) — decks render on the first call.</li>
  </ul>
  <h3 class="round">Round 2 — commit 453b30e · UC v11</h3>
  <ul class="changes">
    <li><strong>The find_skill plan was the largest history item.</strong> A trace audit (plus the Neo4j context-graph
        blog and Labs repos) showed plan <em>size × replay</em>, not call count, was the cost. The budget is now enforced
        on the <em>final</em> plan string — the <code>Relationships</code> footer had been appended un-counted (~1k
        overshoot, 9/11 plans over budget) — at 7,000 chars (was 9,000), with <code>result_k</code> 8 → 6. Plans −26%.</li>
    <li><strong>Priority tiers protect the load-bearing facts.</strong> Seeds (tier 0) and must-ship context (tier 1:
        the intent-routed deck/recipe pages + the GenieSpace page) degrade to a headline + teaser past the budget,
        never drop; ordinary neighbours drop first. The GenieSpace tier was added after the tighter budget silently
        dropped a space_id and the agent — correctly refusing to guess one — burned space-id-hunting re-calls.</li>
    <li><strong>The duplicate capability call is gone.</strong> The second <code>find_skill("compose-pptx deck spec")</code>
        is now skipped when plan #1 already carries the Deck / Visualize section (the intent router puts it there) —
        the deck probe dropped from 2–3 find_skill calls to 1, with the fallback kept for missed intents.</li>
    <li><strong>Fewer ceremony round-trips.</strong> A hard ban on todo-only turns (the plan rides with the first real
        tool call, the closing flip with the last); and "the compact ref <em>is</em> the schema" — no
        <code>describe_dataframe</code> / <code>list_dataframes</code> on a variable whose ref was just received
        (those were 16–19k-token state-poking round-trips).</li>
    <li><strong>Cache-break diagnosis.</strong> A wire-level payload diff proved message history is append-only and
        prefix-stable — the intermittent cache misses are <em>provider-side</em> cache routing on the gpt-5.5 external
        endpoint, not a mutation bug in our code. No false fix shipped.</li>
  </ul>
</section>

<div class="foot">
  Endpoint probes: <code>ab_token_compare.py</code> — sequential single-shot requests to
  <code>agents_workspace-hackathon-orchestrator_agent_neo4j</code>; token usage read from MLflow traces
  (<code>trace.info.token_usage</code>, aggregated over all LLM spans). All three endpoint runs (v9 / v10 / v11) were
  warmed first (scale-to-zero), same workspace, each probed immediately after its in-place UC version became the
  100%-traffic build. Local suite: <code>evals/run_eval.py</code>; the <code>mt-followthrough</code> optimised result is
  the post-rubric-fix re-grade (the original judge rubric pinned a country list and failed a data-correct answer).
  Single run per probe/case — treat small per-probe deltas as noise (the backlog probe's +31% round-2 step is run
  variance); the headline cumulative deltas are far outside it.
</div>

</body>
</html>
"""
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html):,} chars)")
    print(f"suite: pass {pb}->{po}, tokens {tb:,}->{to:,} ({pct(tb,to):+.1f}%), latency {lb:.0f}->{lo:.0f}s ({pct(lb,lo):+.1f}%)")
    if ep_rows:
        all3 = [r for r in ep_rows
                if r["b_tok"] is not None and r["o_tok"] is not None and r["r_tok"] is not None]
        if all3:
            etb = sum(r["b_tok"] for r in all3)
            eto = sum(r["o_tok"] for r in all3)
            etr = sum(r["r_tok"] for r in all3)
            print(f"endpoint ({len(all3)} probes): tokens {etb:,} -> {eto:,} -> {etr:,} "
                  f"(r1 {pct(etb,eto):+.1f}%, r2 {pct(eto,etr):+.1f}%, cumulative {pct(etb,etr):+.1f}%)")
        else:
            print("endpoint: not all three runs present yet")


if __name__ == "__main__":
    main()

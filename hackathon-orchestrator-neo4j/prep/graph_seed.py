"""Turn a catalog profile into a find_skill knowledge-graph SEED.

Emits three artifacts the day-of build consumes:

  graph_seed.json        ontology-valid {nodes, edges} (the data-semantics layer:
                         Domain / GenieSpace / Table / Column / Rule). Drops
                         straight into prep/seed_load.py (or the kg/merge_load.py
                         pipeline) — same schema the LLM extractors emit.

  skill_draft.md         a human-editable companion for the layers that NEED a
                         human/LLM: Metrics, verbatim SqlPatterns, and the
                         Findings ("why") that make the demo. Pre-filled with
                         everything the profile already knows.

  findings_skeleton.json Question/Finding stubs (the insight layer) — fill the
                         claim/evidence and they become graph nodes too.

The data-semantics layer is generated DETERMINISTICALLY (no LLM, no network) so
it runs in a second and is identical run-to-run. You then spend day-of time on
the insight, not on transcribing the schema. Node/edge types match
``neo4j/hackathon-brain/kg/ontology.py`` exactly, so the output is also valid
input to the full extractor pipeline.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SLUG = re.compile(r"[^a-z0-9]+")
_GENERIC_SCHEMAS = {"default", "public", "main", "dbo"}


def canonical_id(node_type: str, name: str) -> str:
    slug = _SLUG.sub("_", (name or "").strip().lower()).strip("_")
    return f"{node_type}:{slug}" if slug else f"{node_type}:_"


def _node(nodes, seen, ntype, name, content, **props):
    nid = canonical_id(ntype, name)
    if nid in seen:
        return name
    seen.add(nid)
    nodes.append({"type": ntype, "name": name, "content": content,
                  "props": {k: str(v) for k, v in props.items() if v not in (None, "")}})
    return name


def _edge(edges, etype, ft, fn, tt, tn, **props):
    edges.append({"type": etype, "from_type": ft, "from_name": fn,
                  "to_type": tt, "to_name": tn,
                  "props": {k: str(v) for k, v in props.items() if v not in (None, "")}})


def _title(s: str) -> str:
    return re.sub(r"[_\-]+", " ", s).strip().title()


def build_seed(profile: dict, catalog_label: str | None = None) -> dict:
    catalog = profile["catalog"]
    label = catalog_label or _title(catalog)
    tables = [t for t in profile.get("tables", []) if t.get("columns") or t.get("row_count") is not None]

    schemas: dict[str, list[dict]] = {}
    for t in tables:
        schemas.setdefault(t["schema"], []).append(t)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    # Catalog-wide convention rule
    fq_rule = "Always fully-qualify tables as `catalog`.`schema`.`table`."
    _node(nodes, seen, "Rule", f"fully-qualify-{_SLUG.sub('-', catalog.lower())}",
          f"{fq_rule} Catalog is `{catalog}`. The data is synced to Lakebase for "
          f"sub-10ms reads but Genie/Spark SQL still address it by UC name.",
          rule_id="R-FQ", statement=fq_rule, severity="medium")

    for schema, stbls in schemas.items():
        dom_name = f"{label}" if schema.lower() in _GENERIC_SCHEMAS else f"{label} · {_title(schema)}"
        tbl_list = ", ".join(t["table"] for t in stbls)
        dom_summary = (f"The {label} hackathon dataset"
                       + (f" (schema `{schema}`)" if schema.lower() not in _GENERIC_SCHEMAS else "")
                       + f" — {len(stbls)} tables: {tbl_list}.")
        _node(nodes, seen, "Domain", dom_name, dom_summary, summary=dom_summary)
        _edge(edges, "APPLIES_TO", "Rule", f"fully-qualify-{_SLUG.sub('-', catalog.lower())}",
              "Domain", dom_name)

        # One Genie space per domain (space_id filled in on event day)
        gs_name = f"{dom_name} Space"
        gs_when = f"Use for any question about {label} ({tbl_list})."
        _node(nodes, seen, "GenieSpace", gs_name,
              f"Genie Space over the {label} tables. Ask natural-language questions; "
              f"it writes SQL over `{catalog}`.`{schema}`.*. {gs_when}",
              space_id="REPLACE_WITH_SPACE_ID_ON_EVENT_DAY", when_to_use=gs_when, summary=dom_summary)
        _edge(edges, "SERVED_BY", "Domain", dom_name, "GenieSpace", gs_name)

        for t in stbls:
            tbl = t["table"]
            fqn = f"{catalog}.{schema}.{tbl}"
            cols = t.get("columns", [])
            rc = t.get("row_count")
            keycols = [c["name"] for c in cols if "key-like" in c.get("flags", [])]
            tcontent = _table_card(t, fqn)
            _node(nodes, seen, "Table", fqn, tcontent, fq_name=fqn,
                  row_count=rc if rc is not None else "",
                  primary_key=t.get("primary_key_guess") or "",
                  grain=(", ".join(keycols[:3]) if keycols else ""),
                  summary=(t.get("comment") or f"{tbl} ({len(cols)} columns)"))
            _edge(edges, "HAS_TABLE", "Domain", dom_name, "Table", fqn)

            # Emit Column + Rule nodes only for columns that carry a gotcha or a join role
            for c in cols:
                flags = c.get("flags", [])
                interesting = any(f in flags for f in (
                    "key-like", "temporal",
                    "string-numeric (CAST to DOUBLE before aggregating)",
                    "all-null", "mostly-null", "constant"))
                if not interesting:
                    continue
                notes = "; ".join(flags)
                _node(nodes, seen, "Column", f"{fqn}.{c['name']}",
                      f"Column `{c['name']}` on `{fqn}` — {c['data_type']}. {notes}.",
                      table=fqn, dtype=c["data_type"], notes=notes)
                _edge(edges, "HAS_COLUMN", "Table", fqn, "Column", f"{fqn}.{c['name']}")

                if "string-numeric (CAST to DOUBLE before aggregating)" in flags:
                    rname = f"cast-{_SLUG.sub('-', (tbl + '-' + c['name']).lower())}"
                    stmt = (f"`{c['name']}` on `{fqn}` is stored as {c['data_type']} but holds "
                            f"numbers — CAST(`{c['name']}` AS DOUBLE) before SUM/AVG/aggregation.")
                    _node(nodes, seen, "Rule", rname, stmt,
                          rule_id=f"R-CAST-{c['name']}", statement=stmt, severity="high",
                          rationale="Aggregating a STRING column errors or sorts lexically.")
                    _edge(edges, "GOTCHA_FOR", "Rule", rname, "Table", fqn)
                    _edge(edges, "APPLIES_TO", "Rule", rname, "Column", f"{fqn}.{c['name']}")

    # JOINS_ON edges from candidate join keys
    for j in profile.get("summary", {}).get("candidate_join_keys", []):
        locs = j["tables"]
        for a in range(len(locs)):
            for b in range(a + 1, len(locs)):
                fa = f"{catalog}.{locs[a]}"
                fb = f"{catalog}.{locs[b]}"
                _edge(edges, "JOINS_ON", "Table", fa, "Table", fb, via=j["column"])

    return {"nodes": nodes, "edges": edges}


def _table_card(t: dict, fqn: str) -> str:
    rc = t.get("row_count")
    head = f"Table `{fqn}`" + (f" — {rc:,} rows." if isinstance(rc, int) else ".")
    lines = [head]
    if t.get("comment"):
        lines.append(t["comment"])
    cols = t.get("columns", [])
    if cols:
        brief = ", ".join(
            f"{c['name']} ({c['base_type']}"
            + ("; CAST→DOUBLE" if "string-numeric (CAST to DOUBLE before aggregating)" in c.get("flags", []) else "")
            + ")"
            for c in cols[:24])
        lines.append("Columns: " + brief + (" …" if len(cols) > 24 else ""))
    if t.get("primary_key_guess"):
        lines.append(f"Likely key: {t['primary_key_guess']}.")
    return "\n".join(lines)


# --- companion artifacts ----------------------------------------------------

def render_skill_draft(profile: dict, seed: dict, label: str) -> str:
    catalog = profile["catalog"]
    ngenie = sum(1 for n in seed["nodes"] if n["type"] == "GenieSpace")
    ntable = sum(1 for n in seed["nodes"] if n["type"] == "Table")
    nrule = sum(1 for n in seed["nodes"] if n["type"] == "Rule")
    L = [
        f"# {label} — skill draft (fill the TODOs, then re-load the graph)",
        "",
        f"> Auto-generated from `profile_{_SLUG.sub('_', catalog.lower()).strip('_')}.json`. "
        f"The graph seed already carries the **data-semantics layer** "
        f"({ngenie} Genie space(s), {ntable} tables, {nrule} rules). "
        "This file is for the layers that need a human/LLM: **metrics, SQL patterns, findings**.",
        "",
        "## 1. Genie spaces — FILL THE space_id",
        "On event day, create one Genie Space per domain over the synced tables, then put its",
        "real `space_id` into the GenieSpace node (the seed ships `REPLACE_WITH_SPACE_ID_ON_EVENT_DAY`).",
        "Dropping a space_id makes find_skill route blind — the agent burns calls guessing.",
        "",
        "## 2. Metrics  (TODO — add the business measures)",
        "For each headline number you'll compute, add a Metric node:",
        "```json",
        json.dumps({"type": "Metric", "name": "recognition_rate",
                    "content": "Share of first-instance asylum decisions that grant protection.",
                    "props": {"formula": "SUM(recognized)/SUM(decided)", "unit": "ratio"}}, indent=2),
        "```",
        "",
        "## 3. SQL patterns  (TODO — the verbatim, proven SQL)",
        "The single highest-value layer: paste the EXACT query (with the CAST gotchas honored).",
        "```json",
        json.dumps({"type": "SqlPattern", "name": "top-hosts-by-volume",
                    "content": "-- when: 'which X has the most Y'\nSELECT ...\nFROM `catalog`.`schema`.`table`\nGROUP BY ... ORDER BY ... DESC",
                    "props": {"question": "which entity has the most …", "notes": "CAST string-numerics first"}}, indent=2),
        "```",
        "Then link it: SqlPattern -ROUTES_TO-> GenieSpace, -COMPUTES-> Metric, -HONORS-> Rule, -VISUALIZED_BY-> ChartRecipe.",
        "",
        "## 4. Findings — the 'why' that wins the demo  (TODO)",
        "See `findings_skeleton.json`. A Finding is a claim + evidence + why; it is what makes",
        "the 'for Good' story land. One strong, honest, CI-backed disparity beats ten dashboards.",
        "",
        "## 5. Detected gotchas (already in the graph as Rule nodes)",
    ]
    sn = profile.get("summary", {}).get("string_numeric_columns", [])
    if sn:
        for g in sn:
            L.append(f"- **CAST**: `{g['table']}`.`{g['column']}` is STRING-but-numeric → CAST to DOUBLE.")
    else:
        L.append("- (none detected — still spot-check sample rows for stringly-typed numbers.)")
    L += ["",
          "## 6. Chart-recipe mapping (pick per finding)",
          "ranked_bar · line_multi · stacked_area_share · lorenz_gini · forest_ci · heatmap_matrix ·",
          "bubble_scatter · choropleth · dumbbell · slope · pyramid · bar_race · iceberg · projection · sankey_corridors.",
          ""]
    return "\n".join(L)


def render_findings_skeleton(profile: dict, label: str) -> dict:
    """Generic 'for Good' question lenses to instantiate against the new data."""
    lenses = [
        ("disparity", "Which groups get systematically different outcomes for the same input?", "forest_ci / heatmap_matrix"),
        ("concentration", "How concentrated is the burden/benefit across entities (top-k share, Gini)?", "lorenz_gini / ranked_bar"),
        ("scale_vs_perception", "What is the true scale vs the part people see?", "iceberg / stat"),
        ("trend_projection", "What is the trajectory, and where does it head if it continues?", "line_multi / projection"),
        ("per_capita_burden", "Who carries the most relative to their size/capacity?", "dumbbell / bubble_scatter"),
        ("flows", "What are the dominant flows/corridors between entities?", "sankey_corridors"),
    ]
    return {
        "_instructions": ("Fill claim/evidence/why for the lenses that fit this dataset; each becomes "
                          "a Finding node (+ a Question node that SURFACES it). Keep claims honest and "
                          "CI/where-possible. Source every number from a SqlPattern."),
        "dataset": label,
        "questions": [
            {"type": "Question", "name": f"{label}: {lens}", "content": q,
             "props": {"intent": lens}, "suggested_chart": chart,
             "finding": {"type": "Finding", "name": f"{label} {lens} finding",
                         "content": "TODO claim", "props": {"claim": "", "evidence": "", "why": "", "window": ""}}}
            for lens, q, chart in lenses
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a find_skill graph seed from a catalog profile.")
    ap.add_argument("--profile", required=True, help="profile_<catalog>.json from profile_catalog.py")
    ap.add_argument("--label", help="human label for the dataset (default: titled catalog name)")
    ap.add_argument("--out", help="output dir (default: same dir as the profile)")
    args = ap.parse_args(argv)

    prof_path = Path(args.profile)
    profile = json.loads(prof_path.read_text())
    label = args.label or _title(profile["catalog"])
    out_dir = Path(args.out) if args.out else prof_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    seed = build_seed(profile, catalog_label=label)
    by_kind: dict[str, int] = {}
    for n in seed["nodes"]:
        by_kind[n["type"]] = by_kind.get(n["type"], 0) + 1

    seed_path = out_dir / "graph_seed.json"
    skill_path = out_dir / "skill_draft.md"
    find_path = out_dir / "findings_skeleton.json"
    seed_path.write_text(json.dumps(seed, indent=2))
    skill_path.write_text(render_skill_draft(profile, seed, label))
    find_path.write_text(json.dumps(render_findings_skeleton(profile, label), indent=2))

    print(f"[seed] {len(seed['nodes'])} nodes ({by_kind}), {len(seed['edges'])} edges")
    print(f"[seed] wrote {seed_path}")
    print(f"[seed] wrote {skill_path}")
    print(f"[seed] wrote {find_path}")
    print(f"[seed] next: fill the TODOs in {skill_path.name}, then "
          f"python -m prep.seed_load --seed {seed_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

---
name: hackathon-agent-skills
description: >
  Top-level skill router for the DAIS-for-Good 2026 hackathon agent
  (India healthcare access / Medical Desert Planner). Routes every user
  question to the appropriate skill. Domain analytics knowledge (metrics,
  rules, SQL patterns, findings, question routing, the India Genie space) is
  served at runtime by the find_skill Neo4j graph — there is no bundled data
  domain folder. This file routes design / chart-guidance questions and
  defers domain analytics to find_skill. Always read this file first, then
  route deeper.
---

# Hackathon Agent — Skill Router

## Purpose

This file is the single entry point for the agent's skill library. Every user
question should be matched to the right destination below. Domain analytics is
not bundled here as static files — it is retrieved on demand from the find_skill
Neo4j graph (which seeds the relevant metrics, rules, SQL patterns, findings,
and the India healthcare Genie space). For design / chart styling, load the
relevant skill's `SKILL.md` for detailed instructions and reference files.

## Available Skills

| Skill | Folder | Purpose | Route when user asks about |
|---|---|---|---|
| Domain analytics | find_skill Neo4j graph (runtime) | Healthcare-access analytics router — NOT a bundled folder. Call `find_skill` with the user's question to retrieve the relevant metrics, rules, SQL patterns, findings, and the India healthcare Genie space, then generate SQL against the Virtue Foundation tables (`facilities`, `india_post_pincode_directory`, `nfhs_5_district_health_indicators`). | District access gaps, zero-facility districts, facility counts by district/state, NFHS-5 health indicators (anaemia, maternal care, etc.), health burden index (HBI), India Post PIN-to-district crosswalk, medical-desert ranking, any India healthcare-access question |
| Design System | [design_system/](design_system/SKILL.md) | Chart styling + guidance — palette, typography, chart-selection matrix, color rules | Chart types, how to visualize, palette, "what chart for X", styling, branding |

## Routing Rules

1. **Data questions → find_skill graph.** Any question about healthcare access,
   facilities, district health indicators, or medical deserts goes through
   `find_skill`: call it with the user's question, follow the retrieved domain
   nodes (rules, SQL patterns, Genie space), and generate SQL only after the
   graph has seeded the relevant context. Do not improvise table names, joins,
   or filters.

2. **Visualization questions → Design System.**
   For chart selection / styling guidance, load `design_system/SKILL.md` and its
   reference files.

3. **Data + chart combined.** When the user asks for data *and* a visualization
   (e.g. "show me the top-10 districts by facility count as a bar chart"),
   resolve the domain context via `find_skill` first (for SQL correctness), then
   Design System (for chart guidance), then render.

4. **No matching skill.** If the question doesn't fit any skill, tell the user
   which skills are currently available and ask them to clarify.

## General Rules

- Resolve domain context via `find_skill` before generating any SQL. Do not
  improvise table names, joins, or filters — use the rules and SQL patterns the
  graph returns.
- Always CAST string-typed numeric columns before aggregation, and guard the
  NFHS-5 suppressed/sentinel values the find_skill rules describe (e.g. cast in a
  subquery and filter out non-numeric sentinels before arithmetic).
- Always state the reporting scope, grouping level, and any coverage caveats in
  your answer. The `facilities` table is a ~10k SAMPLE (coverage, not a census);
  facility claims are self-reported; there is no per-capita measure (no
  population column in these three tables) — surface these honesty caveats when
  relevant.
- If a question requires data not covered by the retrieved domain context, say
  so honestly and suggest the closest answerable question.

## Folder Structure

```
hackathon-skills/
├── SKILL.md                              ← you are here (top-level router)
└── design_system/
    ├── SKILL.md                          ← design system instructions + editorial palette
    └── data-visualisation-chart-guidance/
        ├── SKILL.md                      ← chart selection & design rules
        └── references/                   ← colour rules, chart matrix, guidelines
```

Domain analytics is not a bundled folder — it is served at runtime by the
find_skill Neo4j graph and the India healthcare Genie space.

---
name: hackathon-agent-skills
description: >
  Top-level skill router for the DAIS-for-Good 2026 hackathon agent (dry-run build).
  Routes every user question to the appropriate skill folder. Two skill categories:
  the UNHCR data domains (population stocks + asylum flows, split across two Genie
  spaces) and the design-system / chart-guidance pair. Always read this file first,
  then route deeper.
---

# Hackathon Agent — Skill Router

> **DRY-RUN ARTIFACT.** This `hackathon-skills/` folder is workspace configuration
> for validating the v3 deploy procedure on the Free-Edition hackathon-test
> workspace. It is NOT the hackathon submission. Per DAIS-for-Good rule 4.2(d),
> the actual submission must be authored during the Project Period
> (Jun 15–16 2026 PT) in a fresh repository.

## Purpose

This file is the single entry point for the agent's skill library. Every user
question should be matched to one or more skills below. Do not answer from this
file alone — always load the relevant skill's `SKILL.md` for detailed
instructions and reference files.

## Available Skills

| Skill | Folder | Purpose | Route when user asks about |
|---|---|---|---|
| Data Domains | [domains/](domains/SKILL.md) | Analytics router — splits UNHCR questions across **two** Genie-space domains: `unhcr-population` (stocks: refugees, IDPs, demographics) and `unhcr-asylum-flow` (flows: applications, decisions, durable solutions). The domain router reads the user's question class (stock vs flow) and chooses the right space. | Refugee statistics, displaced populations, asylum applications/decisions, recognition rates, resettlement, country-of-origin or country-of-asylum, IDPs, stateless populations, Sudan, Syria, Ukraine, Venezuela, demographics, time-series of forced migration, top hosts, top origins, any UNHCR Refugee Data Finder question |
| Design System | [design_system/](design_system/SKILL.md) | Chart styling + guidance — palette, typography, chart-selection matrix, color rules | Chart types, how to visualize, palette, "what chart for X", styling, branding |

## Routing Rules

1. **Data questions → Domains skill.** Any question about refugee, displacement,
   or migration data goes to `domains/SKILL.md`, which routes to the specific
   domain (currently only `unhcr-displacement/`). Follow the full routing chain
   before generating SQL.

2. **Visualization questions → Design System.**
   For chart selection / styling guidance, load `design_system/SKILL.md` and its
   reference files. **Note:** no Plotly API reference is included in this
   hackathon-skills folder — chart-rendering library guidance will be added as a
   separate custom skill later (not the k-dense-ai-plotly skill from the v3
   build).

3. **Data + chart combined.** When the user asks for data *and* a visualization
   (e.g. "show me Sudan-origin displacement over time as a line chart"), load
   the Domain skill first (for SQL correctness), then Design System (for chart
   guidance), then render.

4. **No matching skill.** If the question doesn't fit any skill, tell the user
   which skills are currently available and ask them to clarify.

## General Rules

- Always read domain reference files (`business_context.md`, `sql_patterns.md`)
  before generating any SQL. Do not improvise table names, joins, or filters.
- Always CAST string-typed numeric columns before aggregation
  (UNHCR's `solutions.csv` has numeric columns stored as `STRING` with `-`
  as the null sentinel — see domain rule R7).
- Always state the reporting period and grouping level in your answer.
- Only use columns from `business_context.md`. Undocumented columns are
  off-limits for generated SQL.
- If a question requires data not covered by any domain, say so honestly and
  suggest the closest answerable question.

## Folder Structure

```
hackathon-skills/
├── SKILL.md                              ← you are here (top-level router)
├── domains/
│   ├── SKILL.md                          ← stock-vs-flow router across the two domains below
│   ├── unhcr-population/                 ← Genie space A: stocks
│   │   ├── SKILL.md                      ← 9 rules (R0-R10 less R7, R11-R13) + recall guardrail
│   │   ├── business_context.md           ← population, demographics, idmc, countries, years
│   │   ├── sql_patterns.md               ← 10 stock patterns (top hosts, trend, heatmap, crisis dashboard)
│   │   └── genie_config.json             ← Genie space spec for genie_spaces_deploy.py
│   └── unhcr-asylum-flow/                ← Genie space B: flows
│       ├── SKILL.md                      ← 8 rules (R0, R1, R5, R7-R13) + recall guardrail
│       ├── business_context.md           ← asylum_applications, asylum_decisions, solutions, countries, years
│       ├── sql_patterns.md               ← 10 flow patterns (recognition rate, solutions, app-decision merge)
│       └── genie_config.json             ← Genie space spec for genie_spaces_deploy.py
└── design_system/
    ├── SKILL.md                          ← design system instructions + editorial palette
    └── data-visualisation-chart-guidance/
        ├── SKILL.md                      ← chart selection & design rules
        └── references/                   ← colour rules, chart matrix, guidelines
```

## Dataset attribution

All UNHCR data covered by this skill set is sourced from the
**UNHCR Refugee Data Finder** (`api.unhcr.org/population/v1/`), licensed under
**CC BY 4.0**. The agent's final answer to any user query must surface the
source + license in a Methodology / Sources footer (data-journalism skill
convention).

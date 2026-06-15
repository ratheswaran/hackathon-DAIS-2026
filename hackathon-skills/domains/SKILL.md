---
name: hackathon-data-platform
description: >
  Hackathon data platform supervisor skill. Always read this file first to route
  analytics questions to the correct domain skill. Covers two domains from the
  UNHCR Refugee Data Finder: population/demographics (stocks) and asylum
  flow/solutions (flows). Use when the user asks about any refugee, displacement,
  asylum, or migration topic.
---

# Overview

## Purpose

This file is the entry point for all data-analytics questions in the hackathon
dry-run build. It maps each question to the correct domain skill. Do not answer
domain-specific questions from this file alone — always route to the appropriate
domain skill for detailed instructions and reference files.

## Available Domains

The UNHCR dataset is split along the **stock vs flow** axis. Each domain has its
own Genie space backed by the tables relevant to that question class. If a
question spans both (e.g., "how many Afghan refugees are in Germany and what
share of 2023 asylum applications were Afghan?"), query each space separately
and join in `query_stored_dfs`.

| Domain | Folder | Genie Space | Tables | Route when user asks about |
|--------|--------|-------------|--------|---------------------------|
| UNHCR Population & Demographics | [unhcr-population/](unhcr-population/SKILL.md) — absolute path: `/skills/domains/unhcr-population/SKILL.md` | `01f14e10308617a4b984e3668e6471be` | `population`, `demographics`, `idmc`, `countries`, `years` | Refugees abroad, asylum-seeker stocks, IDPs, internally displaced, "forcibly displaced", country of origin, country of asylum, host countries, top hosts, top origins, Sudan/Syria/Ukraine/Venezuela numbers, year-end populations, age-sex demographics, stateless populations, OOC, Others of Concern, "how many refugees / displaced", crisis-overview questions |
| UNHCR Asylum & Solutions | [unhcr-asylum-flow/](unhcr-asylum-flow/SKILL.md) — absolute path: `/skills/domains/unhcr-asylum-flow/SKILL.md` | `01f14e102f8b1f9fa46a17785a02fc4c` | `asylum_applications`, `asylum_decisions`, `solutions`, `countries`, `years` | Asylum applications filed, recognition rates, decision outcomes (recognised/rejected/closed), protection rates, durable solutions, resettlement, naturalisation, returns, repatriation, procedure type (G vs U), decision level, "how many applied / were accepted / were resettled" |

## Routing Rules

1. **Stock vs flow classification.** Ask: is the user asking *how many people
   are currently/end-of-year in a status* (stock → **unhcr-population**) or
   *how many events occurred in a period* (flow → **unhcr-asylum-flow**)?

   | User keyword | Domain |
   |---|---|
   | "How many refugees / displaced / IDPs / asylum-seekers" + reference year | **unhcr-population** |
   | "Population", "stock", "end-of-year", "as of YYYY" | **unhcr-population** |
   | "Top hosts", "top origins", "leaderboard" | **unhcr-population** |
   | "Demographics", "age-sex breakdown", "children", "women" | **unhcr-population** |
   | "Internally displaced", "IDPs" | **unhcr-population** |
   | "Applications filed", "asylum claims", "claims pending" | **unhcr-asylum-flow** |
   | "Recognition rate", "protection rate", "rejected", "decisions" | **unhcr-asylum-flow** |
   | "Resettled", "resettlement", "naturalised", "returned home", "repatriation" | **unhcr-asylum-flow** |
   | "Procedure type", "G vs U", "first instance" | **unhcr-asylum-flow** |
   | "Asylum lottery", "recognition by destination", "fairness", "Simpson's paradox", "odds ratio" | **unhcr-asylum-flow** (S-series; `dec_level='FI'` + `procedure_type='G'` + **TRR**, see R14) |
   | "Concentration", "Gini", "Lorenz", "corridors", "child share", "within region" | **unhcr-population** (S-series) |
   | "Per-capita burden", "refugees per capita", "relative to population", "GDP vs burden", "wealth" | **unhcr-population** + external refs (R16) |

2. **Read the domain's SKILL.md** for its rules (R1–R16) + the
   Instruction #0 recall-as-reference guardrail. For the data-story metrics
   (lottery / Gini / per-capita / matrix / corridors), use the **S-series**
   patterns in each domain's `sql_patterns.md` — they reproduce the validated
   infographic numbers and differ from the plain Q&A patterns (TRR not
   recognition-rate-over-total; the Europe allow-list not `region='Europe'`).

3. **The domain SKILL.md will direct you to its reference files**
   (`business_context.md` for table/column/metric definitions,
   `sql_patterns.md` for proven query templates). Read those before
   generating any SQL.

4. **Cross-domain questions.** If the question spans both domains, query each
   space separately under its skill's rules, then join in
   `query_stored_dfs`. Don't try to write a one-query union — Genie's two
   spaces have non-overlapping data sources by design.

5. **No matching domain.** If the question doesn't fit either domain, tell
   the user which domains are currently available and ask them to clarify.
   Out-of-scope examples: stock market data, weather, sports — redirect.

6. **External reference tables (R16).** Per-capita burden and the GDP-vs-burden
   scatter need `workspace.hackathon.host_population` + `host_gdp` (World Bank,
   CC BY 4.0, loaded once via `deployment/load_reference_tables.py`). These join
   to UNHCR data on `iso`. If they're absent, the per-capita / GDP stories fall
   back to **absolute** host leaderboards — say so; never fabricate populations/GDP.
   When used, add the World Bank source line to the methodology footer.

## General Rules

- Always adapt SQL from the domain's `sql_patterns.md`. Do not improvise table
  names, joins, or filters not documented in the reference files.
- Always CAST string-typed numeric columns before aggregation (e.g.
  `unhcr-asylum-flow.solutions` numeric columns are strings — see R7).
- Always state the reporting period and grouping level in your answer.
- UNHCR data is **annual** — no monthly figures. Reject "in March 2024"
  phrasing (R5).
- If a question requires data not covered by any domain, say so honestly and
  suggest the closest answerable question.
- **Column Quality Control:** only use columns from the relevant
  `business_context.md`. Undocumented columns are off-limits for generated
  SQL.

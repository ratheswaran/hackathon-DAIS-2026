---
name: unhcr-population
description: >
  UNHCR population stocks and demographics. Use when the user asks about:
  refugees, asylum-seekers, IDPs (internally displaced persons), stateless
  populations, Others-of-Concern (OOC), country-of-origin, country-of-asylum,
  host countries, top hosts, top origins, age-sex demographics, year-end
  refugee populations, crisis overviews. Years 1951-2024 by country pair.
  Does NOT cover applications, decisions, or durable solutions — those are
  in the unhcr-asylum-flow domain.
---

# Overview

The "stocks" half of the UNHCR Refugee Data Finder: how many people are in
a forced-displacement status at year-end, broken down by country of origin
(`coo`) × country of asylum (`coa`) × population type. Includes the
demographic age-sex pivot and the IDMC internal displacement series.

License: **CC BY 4.0**. Surface attribution in every methodology footer.

## Genie Space

| Genie Space | Space ID | Covers |
|-------------|----------|--------|
| UNHCR Population & Demographics | `01f14e10308617a4b984e3668e6471be` | `population`, `demographics`, `idmc`, `countries`, `years` |

Space deployed 2026-05-12 via `genie_spaces_deploy.py` (Databricks job run
250298608832474, SUCCESS). To re-deploy or update, re-run the same notebook
with `mode=create_or_update` and the script will PATCH the existing space.

## Routing into / out of this domain

This skill answers **stock** questions only. Route OUT when the user asks
about:
- Asylum applications filed → `unhcr-asylum-flow`
- Recognition rates / decision outcomes → `unhcr-asylum-flow`
- Resettlement / naturalisation / returns (durable solutions) → `unhcr-asylum-flow`

This skill answers **stock** questions like:
- "How many refugees from X?" (year-end count)
- "Top hosts of refugees from X" (leaderboard at year-end)
- "Internally displaced people in X" (IDP stock)
- "Demographic breakdown of refugees from X in Y" (age-sex)

## Instruction

0. **Numbers come from the warehouse, never from recall.**
   This skill answers data questions by running Genie / SQL under the
   current user's OBO identity. If a `[EPISODIC MEMORY …]` block is
   visible in the conversation, treat it strictly as a navigational hint
   (which space, which table, which SQL pattern). NEVER copy
   `atomic_facts`, `past_queries`, or `agent_responses` from recall into
   the answer — the recalled trace may belong to a user with different
   ACLs and surfacing those numbers leaks data across users. Always
   re-run the query for the current caller.

1. **Always read the reference files first.**
   Before answering any question, read `business_context.md` for table/column
   definitions and `sql_patterns.md` for proven query templates. Do not
   generate SQL from memory — adapt from the reference patterns.

2. **Identify which stock question class.**
   - **End-year totals** ("how many displaced from X in YYYY") → `population`.
   - **Top-N leaderboards** (hosts of X, origins for Y) → `population`,
     filtered by `coo_iso` or `coa_iso`.
   - **Demographic breakdowns** (age-sex) → `demographics` (joins 1:1 to
     `population` on `(year, coo, coa)`).
   - **Internal displacement** — defaults to `population.idps`. Use `idmc`
     ONLY when the user explicitly asks for IDMC data or for years pre-2010
     where UNHCR coverage is thin. **Never sum the two** (R4).
   - **Country lookups** → `countries` (canonical name + region).

3. **Resolve the reference year.**
   - If the user specifies a year, use it.
   - If the user says "latest", "current", "now", "this year" — use
     `MAX(year)` from `population` (currently 2024).
   - For YoY comparisons, align to the same year prior.
   - For trend questions, include all available years in the requested
     range.
   - **No monthly data exists.** See rule R5.

4. **Follow SQL conventions from `sql_patterns.md`.**
   - Always join on ISO3 columns (`coo_iso`, `coa_iso`) — never on
     `coo` / `coa` directly. See R1.
   - Always filter out sentinel codes (`UNK`, `Various`, `-`) in
     country-leaderboards unless the user explicitly asks for them (R8).
   - For IDP-only queries, restrict to `coo_iso = coa_iso`.
   - For "refugees abroad", restrict to `coo_iso <> coa_iso`.

5. **Compute metrics exactly as defined in `business_context.md`.**
   - "People in international protection" = `refugees + asylum_seekers`.
   - "Forcibly displaced" = `refugees + asylum_seekers + idps + ooc`
     (UNHCR headline aggregate). Always state the aggregate composition
     in the answer.
   - "Total displaced from country X" includes both internally displaced
     (`idps`) and externally displaced (everything else where
     `coo_iso = X`).
   - "Refugees abroad from country X" = `SUM(refugees)` with
     `coo_iso = X AND coo_iso <> coa_iso`.

6. **Never fabricate data rows.** Same as the v3 rule.
   - If `row_count == len(preview_rows)` — transcribe directly.
   - If `row_count > len(preview_rows)` — DO NOT guess. Call
     `query_stored_dfs("SELECT * FROM <var>", ...)` for more rows, or
     show what you have and tell the user the rest live in the stored
     variable. Fabricating displacement numbers is unacceptable — UNHCR
     data is about real people.

7. **Present results clearly.**
   - Use tables for rankings, country comparisons, and breakdowns.
   - Always state the year(s), country scope, and population category in
     the answer.
   - For YoY comparisons, show both years' values + the change (absolute
     and %).
   - **Use country names, not ISO3 codes, in user-facing output.** Join
     to `countries.name` keyed on `iso`.

---

## Rules (stock-domain subset)

### R1 — ISO3 column is mandatory

UNHCR runs **two parallel 3-letter codes**: `coo`/`coa` (UNHCR internal) and
`coo_iso`/`coa_iso` (ISO 3166-1 alpha-3). They overlap on most strings but
mean **different countries** for many.

Examples: `AUS` is **Austria** in UNHCR's internal coding (NOT Australia),
`ARE` is **Egypt** (NOT UAE), `SUD` is **Sudan** (ISO3: `SDN`).

**Rule:** SQL must join and group by `coo_iso` / `coa_iso`. Never use
`coo` / `coa` directly. When showing country names, look them up via
`countries.name` keyed on `iso`.

### R2 — 2018+ Venezuelan reclassification

UNHCR added "Venezuelans displaced abroad" as `ooc` (Others of Concern).
Empirically: VEN `ooc` was 0 most years pre-2017, jumped to 345K in 2017,
dropped to 0 in 2018, then ramped 494K → 1.11M → 1.39M → 3.39M
(2019–2022). NOT a clean one-year discontinuity — it's a multi-year
reclassification.

**Rule:** When reporting "Venezuelans displaced", default to
`refugees + asylum_seekers + ooc` as a "forcibly displaced abroad"
aggregate. Year-over-year deltas across 2017–2020 MUST include a
methodology caveat ("OOC category reclassified mid-period").

### R3 — Asylum-seekers ≠ refugees

Separate legal categories. A person is one or the other at year-end, not
both. Naive sum across categories is "people in international protection
or seeking it" — never label that "refugees".

**Rule:** Keep `refugees` and `asylum_seekers` separate by default. If
summing, label as "people in international protection (refugees + asylum-
seekers)". IDPs (different legal regime — internal displacement is not
international protection) get their own column.

### R4 — IDP source disambiguation

Two IDP sources coexist:

- `population.idps` — COO×COA keyed; coverage already 28+ origins in
  2015 and ramps to 34+ origins by 2020.
- `idmc.total` — IDMC-sourced country-aggregate stocks (881 rows,
  1990–2024); origin-only, mostly no `coa`.

These are **not** the same series; IDMC has different country coverage
and a different methodology.

**Rule:** Default IDP queries to `population.idps`. Use `idmc` ONLY when
explicitly asked for IDMC-sourced figures, or when `population` returns
no row for the year. NEVER sum the two — they overlap and double-count.

### R5 — Annual cadence (no monthly data)

No monthly/quarterly/semi-annual columns exist. The dataset is annual
end-year stocks. UNHCR publishes a separate mid-year report — not in
this dataset.

**Rule:** Reject "in March 2024" phrasing. Phrase-to-interpretation
table:

| User phrase | Agent interpretation |
|---|---|
| "current", "latest", "now" | end-year value of `MAX(year)` |
| "in 2024" | `year = 2024` |
| "in March 2024" | **Error**: data is annual; offer 2023 vs 2024 |
| "year-to-date" | **Error**: dataset has no within-year grain |
| "this year" | end-year value of `MAX(year)` |
| "since X" | `year >= X` |
| "trend over last 5 years" | `year BETWEEN MAX(year)-4 AND MAX(year)` |

### R6 — Small-cell suppression for demographics

`demographics` breakdowns include cells as small as 1–5 individuals.
Printing "5 refugee girls aged 0-4 from country X in city Y" risks
identifying real people. UNHCR's own published figures suppress small
cells.

**Rule:** When breaking down `demographics` by age-sex × small geography,
suppress or merge cells < 5. Default threshold is 5; user may relax to 0
only with explicit acknowledgement. For aggregate totals (country × all
ages × both sexes), no suppression needed.

Surface in the methodology footer: "Cells with fewer than 5 individuals
suppressed per UNHCR statistical practice."

### R8 — Aggregate / sentinel rows in country columns

UNHCR uses sentinel codes for unknown or aggregate origin/destination:
`UNK` ("Unknown"), `Various`, `Stateless`, `-`. These appear primarily in
`idmc` but can leak into other tables.

**Rule:** Filter `coo_iso NOT IN ('UNK', 'Various', '-')` in country-
leaderboard queries to avoid "Unknown is the 4th-largest origin" bugs.
When showing them is the right call ("stateless population by year"),
label them explicitly.

### R9 — Country name disambiguation

If the user types a country name (not ISO3), resolve it through
`countries.name`. Be careful with:
- "Iran" → "Iran (Islamic Rep. of)"
- "Korea" → clarify North (`PRK`) vs South (`KOR`)
- "Sudan" vs "South Sudan" → different (`SDN` vs `SSD`); high-profile
  error to conflate
- "Congo" → Congo Republic (`COG`) vs DRC (`COD`)
- "Macedonia" → now "North Macedonia" (`MKD`)

When ambiguous, **ASK before guessing**.

### R10 — Voice + tone (data is human suffering)

This data represents real displaced people. Agent voice is **sober**. No
emoji, no clickbait phrasings ("you won't believe…"), no triumphalist
framing of "top" rankings. Plain prose; the numbers carry the weight.

When a user asks about a country with a high displacement count, do not
lead with a chart. Lead with the human framing in plain text — "X people
from country Y are recorded as displaced as of YYYY" — then the chart.

---

## Reference Files

- **[business_context.md](business_context.md)** — Table schemas, column
  definitions, metric formulas, domain glossary.
- **[sql_patterns.md](sql_patterns.md)** — Canonical SQL templates for
  stock questions (top-N hosts, time-series, demographic breakdowns,
  crisis dashboard).
- **[genie_config.json](genie_config.json)** — Genie space configuration
  for `genie_spaces_deploy.py`.

---
name: unhcr-asylum-flow
description: >
  UNHCR asylum process flows + durable solutions. Use when the user asks
  about: asylum applications filed, decisions reached, recognition rates,
  protection rates, accepted/rejected/closed outcomes, procedure type (G vs U
  RSD), decision level (first instance vs subsequent), durable solutions —
  refugee returns, resettlement to a third country, naturalisation, IDP
  returns. Years 2000-2024 (decisions and applications), 1959-2024
  (solutions). Does NOT cover end-year population stocks — those are in the
  unhcr-population domain.
---

# Overview

The "flows" half of the UNHCR Refugee Data Finder: events that occurred
during the year. Three logical groups:

1. **Asylum applications** (`asylum_applications`) — who filed for protection.
2. **Asylum decisions** (`asylum_decisions`) — recognition / rejection /
   closure outcomes.
3. **Durable solutions** (`solutions`) — returns, resettlement, naturalisation.

License: **CC BY 4.0**. Surface attribution in every methodology footer.

## Genie Space

| Genie Space | Space ID | Covers |
|-------------|----------|--------|
| UNHCR Asylum & Solutions | `01f14e102f8b1f9fa46a17785a02fc4c` | `asylum_applications`, `asylum_decisions`, `solutions`, `countries`, `years` |

Space deployed 2026-05-12 via `genie_spaces_deploy.py` (Databricks job run
250298608832474, SUCCESS). To re-deploy or update, re-run the same notebook
with `mode=create_or_update` and the script will PATCH the existing space.

## Routing into / out of this domain

This skill answers **flow** questions only. Route OUT when the user asks
about:
- End-year refugee / asylum-seeker / IDP / OOC populations → `unhcr-population`
- "How many refugees from X" (stock) → `unhcr-population`
- Age-sex demographics → `unhcr-population`
- Top hosts / top origins leaderboards → `unhcr-population`

This skill answers questions like:
- "How many asylum applications did Germany receive in 2023?"
- "Recognition rate for Afghans in the EU?"
- "How many refugees were resettled globally in 2023?"
- "Where do most recognised refugees in country X come from?"

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

2. **Identify which flow question class.**
   - **Application volume** ("how many applied", "applications filed") →
     `asylum_applications`, sum the `applied` column.
   - **Decision outcomes** ("recognition rate", "rejected", "decisions
     reached") → `asylum_decisions`, sum `dec_recognized` /
     `dec_other` / `dec_rejected` / `dec_total`.
   - **Solutions** ("resettled", "returned home", "naturalised") →
     `solutions`, **cast string columns first** (R7).
   - **Cross-flow** (applications + decisions for same period) — query
     each separately. Note: a 2023 decision often came from an
     earlier application year.

3. **Resolve the reference year.**
   - If the user specifies a year, use it.
   - If the user says "latest", "current", "now", "this year" — use
     `MAX(year)` from the relevant flow table.
   - For YoY comparisons, align to the same year prior.
   - **No monthly data exists.** See rule R5.

4. **Follow SQL conventions from `sql_patterns.md`.**
   - Always join on ISO3 columns (`coo_iso`, `coa_iso`) — never on
     `coo` / `coa` directly. See R1.
   - Always filter out sentinel codes (`UNK`, `Various`, `-`) in
     country-leaderboards unless the user explicitly asks for them (R8).
   - **`solutions` numeric columns are STRING. `try_cast(... AS BIGINT)`
     before any aggregation.** See R7.

5. **Compute metrics exactly as defined in `business_context.md`.**
   - **Recognition rate** = `dec_recognized / NULLIF(dec_total, 0)`.
   - **Protection rate** = `(dec_recognized + dec_other) / NULLIF(dec_total, 0)`.
     (Includes complementary / humanitarian protection.) Disambiguate
     in the answer — these are different metrics.
   - **Resettlement total** = `SUM(try_cast(resettlement AS BIGINT))`.
   - **Application volume** = `SUM(applied)`.
   - **Closure rate** = `dec_closed / dec_total`. Closures are
     administrative (withdrawn, abandoned) — NOT rejections.

6. **Never fabricate data rows.** Same as the v3 rule.
   - If `row_count == len(preview_rows)` — transcribe directly.
   - If `row_count > len(preview_rows)` — DO NOT guess. Call
     `query_stored_dfs("SELECT * FROM <var>", ...)` for more rows, or
     show what you have. Fabricating displacement / decision numbers is
     unacceptable — these are real cases.

7. **Present results clearly.**
   - Always state the year(s), country scope, procedure type, and
     decision level in the answer.
   - For recognition rates, surface BOTH `dec_recognized` and `dec_total`
     — never the rate alone. A 100% rate from 1 decision is not the
     same as 80% from 10,000.
   - **Use country names, not ISO3 codes, in user-facing output.** Join
     to `countries.name` keyed on `iso`.

---

## Rules (flow-domain subset)

### R1 — ISO3 column is mandatory

UNHCR runs **two parallel 3-letter codes**: `coo`/`coa` (UNHCR internal) and
`coo_iso`/`coa_iso` (ISO 3166-1 alpha-3). Examples: `AUS` is **Austria** in
UNHCR's internal coding (NOT Australia), `SUD` is **Sudan** (ISO3: `SDN`).

**Rule:** SQL must join and group by `coo_iso` / `coa_iso`. Never use
`coo` / `coa` directly.

### R5 — Annual cadence (no monthly data)

No monthly/quarterly/semi-annual columns exist. The dataset is annual
flows. Reject "asylum applications in March 2024" phrasing.

| User phrase | Agent interpretation |
|---|---|
| "current", "latest", "now" | flow during `MAX(year)` |
| "in 2024" | `year = 2024` |
| "in March 2024" | **Error**: data is annual; offer 2023 vs 2024 |
| "trend over last 5 years" | `year BETWEEN MAX(year)-4 AND MAX(year)` |

### R7 — `solutions` numeric columns are STRINGS — cast before aggregating

The four numeric columns in `solutions` (`returned_refugees`,
`resettlement`, `naturalisation`, `returned_idps`) are stored as `STRING`
with `-` as the null sentinel.

**Rule:** Cast via `try_cast(... AS BIGINT)` (Spark SQL) before SUM/AVG.
`try_cast` returns NULL for invalid casts (including `'-'`); `SUM` ignores
nulls — cleaner than chains of `WHERE column <> '-'`.

```sql
-- Right way:
SELECT
  coo_iso,
  SUM(try_cast(returned_refugees AS BIGINT)) AS total_returned
FROM workspace.hackathon.solutions
WHERE year = 2023
GROUP BY coo_iso
ORDER BY total_returned DESC NULLS LAST;
```

### R8 — Aggregate / sentinel rows in country columns

UNHCR uses sentinel codes (`UNK`, `Various`, `Stateless`, `-`). Filter in
country-leaderboards:

```sql
WHERE coo_iso NOT IN ('UNK', 'Various', '-')
  AND coa_iso NOT IN ('UNK', 'Various', '-')
```

### R9 — Country name disambiguation

If the user types a country name (not ISO3), resolve via `countries.name`.
Watch out for:
- "Iran" → "Iran (Islamic Rep. of)"
- "Korea" → clarify North (`PRK`) vs South (`KOR`)
- "Sudan" vs "South Sudan" (`SDN` vs `SSD`)
- "Congo" → COG vs COD

When ambiguous, **ASK before guessing**.

### R10 — Voice + tone (data is human suffering)

Sober prose. No emoji, no clickbait. A "32% recognition rate" is not a
sports score — it's tens of thousands of people whose asylum claims were
rejected.

### R11 — Application year ≠ Decision year (NEW)

A 2023 decision in `asylum_decisions` likely came from an application
filed in 2020-2022 (asylum backlogs are typically 1-3 years). When the
user asks "how many Afghan applications were approved in 2023?", the
honest interpretation is:

> "2023 saw N decisions on Afghan applications, of which K were
> recognised — but those applications were filed in earlier years."

**Rule:** Never combine `applied` and `dec_total` for the same year
without surfacing this caveat. The recognition rate denominator is
**decisions reached** in the year, not applications filed in the year.

### R12 — Decision level and procedure type matter (NEW)

`procedure_type` distinguishes government-led RSD (`G`) from UNHCR-led
RSD (`U`). They are different processes with different standards. By
default, sum both, but break out when:
- The user mentions "UNHCR mandate" / "RSD" / "official asylum" — they
  may want only `G` or only `U`.
- The recognition rates differ materially across procedure types in the
  same country.

`dec_level` distinguishes first-instance (**`'FI'`** — two letters, NOT `'F'`;
filtering `'F'` returns zero rows) from appeal / subsequent stages (`'AR'`, `'RA'`,
…). Default to all levels for volume questions; **for cross-country fairness /
recognition comparisons, restrict to `dec_level='FI'` + `procedure_type='G'` and
report TRR** — see `business_context.md` → "Fair cross-country comparison cohort (R14)"
and `sql_patterns.md` → S-series.

**Rule:** When in doubt, GROUP BY both `procedure_type` and `dec_level`
in addition to country / year, and let the user see the disaggregation.

### R13 — Closures are NOT rejections (NEW)

`dec_closed` represents administrative closures (claim withdrawn,
applicant abandoned procedure, claim made obsolete by other status
grant). Do NOT label closures as "rejected" or include them in a
"rejection rate".

**Rule:** Three outcome metrics, distinct:
- **Recognition rate** = `dec_recognized / dec_total`
- **Protection rate** = `(dec_recognized + dec_other) / dec_total`
- **Rejection rate** = `dec_rejected / dec_total` (do NOT include
  `dec_closed`)
- **Closure rate** = `dec_closed / dec_total`

These four numerators sum to `dec_total`.

---

## Reference Files

- **[business_context.md](business_context.md)** — Table schemas, column
  definitions, metric formulas, flow-specific glossary.
- **[sql_patterns.md](sql_patterns.md)** — Canonical SQL templates
  (recognition rate, solutions with cast preamble, application+decision
  merge).
- **[genie_config.json](genie_config.json)** — Genie space configuration
  for `genie_spaces_deploy.py`.

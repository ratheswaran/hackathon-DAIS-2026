# UNHCR Asylum & Solutions — Business Context

> Table schemas, column meanings, metric formulas, and domain glossary for
> the flows half of the UNHCR Refugee Data Finder. Read this BEFORE writing
> SQL. For stocks (population, demographics, IDMC) see the
> `unhcr-population` domain.

All tables live in **`workspace.hackathon`** on the hackathon-test workspace.
Row counts captured 2026-05-12 against the CSV snapshot pulled 2026-05-06.

---

## Domain glossary

| Term | Definition | Source |
|---|---|---|
| **Application** | A claim for international protection filed with a state or UNHCR in a given year. | `asylum_applications.applied` |
| **Decision** | An outcome reached on an application in a given year (may have been filed in a prior year). | `asylum_decisions.dec_total` |
| **Recognised decision** | Application granted refugee status under the 1951 Convention or UNHCR mandate. | `asylum_decisions.dec_recognized` |
| **Other positive decision** | Application granted complementary or humanitarian protection (not refugee status, but protected). | `asylum_decisions.dec_other` |
| **Rejected decision** | Application denied on the merits. | `asylum_decisions.dec_rejected` |
| **Closed decision** | Administratively closed (applicant withdrew, abandoned, or claim made moot). NOT a rejection. | `asylum_decisions.dec_closed` |
| **Recognition rate** (over total) | `dec_recognized / dec_total` — includes closures in the denominator | derived |
| **Protection rate** (over total) | `(dec_recognized + dec_other) / dec_total` — broader; includes complementary protection | derived |
| **Total Recognition Rate (TRR)** | `(dec_recognized + dec_other) / (dec_recognized + dec_other + dec_rejected)` — **denominator EXCLUDES `dec_closed` and is NOT `dec_total`.** This is the comparative "did the substantive claim succeed" metric used for the asylum-lottery / cross-country fairness stories. | derived |
| **Rejection rate** | `dec_rejected / dec_total` | derived |
| **Procedure type — G** | Government-led RSD (Refugee Status Determination). The state itself decides asylum claims. | `procedure_type = 'G'` |
| **Procedure type — U** | UNHCR-led RSD. UNHCR conducts RSD on behalf of (or instead of) the state — typical in countries where the state has no asylum system. | `procedure_type = 'U'` |
| **Decision level — FI** | **First-instance decision.** ⚠ The data value is the two-letter **`'FI'`** (≈58% of rows), **NOT `'F'`** — there is no `'F'` value. Filtering `dec_level = 'F'` returns ZERO rows. | `dec_level = 'FI'` |
| **Decision level — appeal/other** | Appeal / subsequent / administrative-review levels (e.g. `'AR'`, `'RA'`, `'SA'`, `'JR'`). Values vary by country; inspect with `SELECT DISTINCT dec_level` before assuming. | `dec_level <> 'FI'` |
| **Durable solution** | Long-term resolution of refugee status. Three pathways: return, resettlement, naturalisation. | `solutions` table |
| **Return** | Refugee or IDP voluntarily returns to country of origin. | `solutions.returned_refugees`, `solutions.returned_idps` |
| **Resettlement** | Refugee transferred from country of asylum (COA) to a third state for permanent residence. | `solutions.resettlement` |
| **Naturalisation** | Refugee acquires citizenship of the country of asylum. | `solutions.naturalisation` |

---

## Country-code dual system — the #1 footgun

UNHCR carries **two parallel 3-letter codes** per country. They overlap on
most strings but mean different countries for many. Examples: `AUS` is
**Austria** (not Australia) in UNHCR's internal coding; `SUD` is **Sudan**
(ISO3: `SDN`).

| Column | System | Note |
|---|---|---|
| `coo` / `coa` | UNHCR internal | Use ONLY for raw inspection. Never join on these. |
| `coo_iso` / `coa_iso` | ISO 3166-1 alpha-3 | **Canonical join key.** |
| `coo_name` / `coa_name` | Display name | Stable; safe to surface to users. |

**Rule (R1):** Always join + group by `coo_iso` / `coa_iso`. Look up display
names from `countries.name` keyed on `iso`.

---

## Tables

### 1. `workspace.hackathon.asylum_applications` — 114,588 rows

Annual **flow** of asylum applications filed. Years 2000–2024.

| Column | Type | Description |
|---|---|---|
| `year` | INT | Filing year. |
| `coo_id`, `coo_name`, `coo`, `coo_iso` | mixed | Applicant's country of origin. |
| `coa_id`, `coa_name`, `coa`, `coa_iso` | mixed | Country where application was filed. |
| `procedure_type` | STRING | `G` = government-led RSD, `U` = UNHCR-led RSD. |
| `app_type` | STRING | Application type (new, appeal, repeat). Domain values to be confirmed at query time. |
| `dec_level` | STRING | Decision level. First instance is **`'FI'`** (two letters), NOT `'F'`. Appeal/subsequent levels use other codes (`'AR'`, `'RA'`, …). |
| `app_pc` | STRING | `P` = persons, `C` = cases. Different units (a "case" can cover a family). Default to filtering `app_pc = 'P'` when comparing to per-person counts. |
| `applied` | INT | Number of applications filed at this row's combination of (year, coo, coa, procedure, app_type, dec_level, app_pc). |

### 2. `workspace.hackathon.asylum_decisions` — 108,444 rows

Annual **flow** of asylum decisions reached. Years 2000–2024.

| Column | Type | Description |
|---|---|---|
| `year` | INT | Decision year. |
| `coo_id`, `coo_name`, `coo`, `coo_iso` | mixed | Applicant's country of origin. |
| `coa_id`, `coa_name`, `coa`, `coa_iso` | mixed | Country reaching the decision. |
| `procedure_type` | STRING | `G` (government-led) or `U` (UNHCR-led). For cross-country *fairness* comparisons use **`'G'`** — UNHCR-led RSD (`'U'`) happens in countries with no state asylum system and is not comparable. |
| `dec_level` | STRING | Decision level. First instance = **`'FI'`** (two letters, NOT `'F'`). Other values are appeal/subsequent (`'AR'`, `'RA'`, …). `SELECT DISTINCT dec_level` to confirm. |
| `dec_pc` | STRING | `P` (persons) or `C` (cases). Filter `dec_pc = 'P'` for per-person comparisons. |
| `dec_recognized` | INT | Decisions granting refugee status. |
| `dec_other` | INT | Other positive outcomes (complementary / humanitarian protection). |
| `dec_rejected` | INT | Rejected decisions (denied on merits). |
| `dec_closed` | INT | Administrative closures (withdrawn / abandoned). **NOT a rejection.** |
| `dec_total` | INT | Total decisions reached. Should equal sum of the four. |

**Outcome metrics — four distinct, mutually exclusive:**

```
recognition_rate = dec_recognized / NULLIF(dec_total, 0)     -- refugee status grant (incl. closures in denom)
protection_rate  = (dec_recognized + dec_other) / NULLIF(dec_total, 0)
rejection_rate   = dec_rejected / NULLIF(dec_total, 0)       -- denied on merits
closure_rate     = dec_closed / NULLIF(dec_total, 0)         -- administrative

-- Total Recognition Rate (TRR) — the comparative "did the substantive claim succeed" metric.
-- Denominator EXCLUDES dec_closed. This is what the asylum-lottery + regression stories report.
trr = (dec_recognized + dec_other)
      / NULLIF(dec_recognized + dec_other + dec_rejected, 0)
```

**Critical (R13):** Closures are NOT rejections. They reflect withdrawn /
abandoned claims, not negative decisions on the merits. Because closures vary
hugely by country (procedural, not substantive), the cross-country fairness
stories use **TRR** (closures excluded), not `recognition_rate` over `dec_total`.
Reporting `recognition_rate` over `dec_total` understates protection wherever
closure rates are high and is NOT comparable across states.

### 3. `workspace.hackathon.solutions` — 20,412 rows

Annual **flow** of durable-solution outcomes. Years 1959–2024.

| Column | Type | Description |
|---|---|---|
| `year` | INT | Year. |
| `coo_id`, `coo_name`, `coo`, `coo_iso` | mixed | Origin country. |
| `coa_id`, `coa_name`, `coa`, `coa_iso` | mixed | Asylum country (or third country for resettlement). |
| `returned_refugees` | **STRING** | Refugees who returned to COO in that year. **`-` = null.** Cast via `try_cast(... AS BIGINT)` per R7. |
| `resettlement` | **STRING** | Refugees resettled from COA to a third country in that year. Same string/null pattern. |
| `naturalisation` | **STRING** | Refugees who naturalised in COA in that year. |
| `returned_idps` | **STRING** | IDPs who returned home in that year. |

**Critical (R7):** The four numeric columns are STRING with `-` as null.
Cast and (implicitly) filter with `try_cast` before aggregating.

### 4. `workspace.hackathon.countries` — 232 rows

Reference table for ISO3 → country name and metadata.

| Column | Type | Description |
|---|---|---|
| `0` | INT | Pandas index column carried from CSV — **ignore**. |
| `id` | INT | UNHCR internal numeric country ID. |
| `code` | STRING | UNHCR internal 3-letter code (joins to `*.coo`/`coa`). |
| `iso` | STRING | **ISO3 code.** Joins to `*_iso` columns. |
| `iso2` | STRING | ISO2 code. |
| `name` | STRING | **Canonical display name.** Use for user-facing output. |
| `nationality` | STRING | Demonym ("German", "Sudanese"). |
| `majorArea`, `region` | STRING | UN geographic regions. |
| `nameFr`, `majorAreaFr`, `regionFr` | STRING | French equivalents. |

**Join pattern:** `JOIN workspace.hackathon.countries c ON c.iso = ad.coo_iso`.

### 5. `workspace.hackathon.years` — 76 rows

Reference list of valid year values (1951–2026 incl. placeholder rows for
2025–2026 with no data yet). One INT column: `year`.

---

## Key derived metrics (flow domain)

| Metric | Formula |
|---|---|
| **Total Recognition Rate (TRR)** ★ | `SUM(dec_recognized + dec_other) * 1.0 / NULLIF(SUM(dec_recognized + dec_other + dec_rejected), 0)` — closures excluded. **Use this for fairness / lottery / regression stories.** |
| **Recognition rate** (over total) | `SUM(dec_recognized) * 1.0 / NULLIF(SUM(dec_total), 0)` |
| **Protection rate** (over total) | `SUM(dec_recognized + dec_other) * 1.0 / NULLIF(SUM(dec_total), 0)` |
| **Rejection rate** | `SUM(dec_rejected) * 1.0 / NULLIF(SUM(dec_total), 0)` |
| **Closure rate** | `SUM(dec_closed) * 1.0 / NULLIF(SUM(dec_total), 0)` |
| **Application volume** | `SUM(applied)` from `asylum_applications` |
| **Resettlement total** | `SUM(try_cast(resettlement AS BIGINT))` from `solutions` |
| **Naturalisation total** | `SUM(try_cast(naturalisation AS BIGINT))` from `solutions` |
| **Refugee return total** | `SUM(try_cast(returned_refugees AS BIGINT))` from `solutions` |
| **IDP return total** | `SUM(try_cast(returned_idps AS BIGINT))` from `solutions` |

---

## Fair cross-country comparison cohort (R14) — the "asylum lottery" base

The asylum-lottery, recognition-matrix, Simpson's-paradox, and logistic-regression
stories all compare destinations on a **like-for-like** cohort. Using the raw
table without this cohort produces non-comparable rates and wrong headlines.

**The cohort filter (apply ALL):**

```sql
WHERE dec_level = 'FI'                  -- first instance only (NOT 'F')
  AND procedure_type = 'G'              -- government-led RSD only (drop UNHCR 'U')
  AND dec_pc = 'P'                      -- persons, not cases
  AND coa_iso IN (<EUROPE_ALLOWLIST>)   -- comparable jurisdictions only
  AND coo_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
```

**EUROPE_ALLOWLIST** — EU-27 + EFTA + UK (the story's 30-ISO destination set;
`countries.region = 'Europe'` is a *looser* approximation and will NOT reproduce
the story cohort):

```
'AUT','BEL','BGR','HRV','CYP','CZE','DNK','EST','FIN','FRA','DEU','GRC','HUN',
'IRL','ITA','LVA','LTU','LUX','MLT','NLD','POL','PRT','ROU','SVK','SVN','ESP',
'SWE','ISL','NOR','CHE','GBR','LIE'
```

> ⚠ Reproducibility: the validated story cohort (Afghan first-instance, EU/EFTA/UK,
> 2023) is **n ≈ 472,165** decisions across 17 destinations with a non-zero cell.
> Headlines: Afghans recognised **≈96% in Germany vs ≈40% in Sweden** (TRR). If your
> query returns a different n or 0 rows, re-check `dec_level='FI'` (not `'F'`) and the
> allow-list before reporting numbers.

**Cell suppression (R15):** when building an origin×destination matrix or any
per-cell rate, suppress cells with `SUM(dec_recognized+dec_other+dec_rejected) < 300`
(too few decisions to report a stable rate). Annotate suppressed cells, don't drop silently.

---

## Sentinel values to filter

| Where | Sentinel | Filter pattern |
|---|---|---|
| `coo_iso`, `coa_iso` | `UNK`, `Various`, `-` | `... NOT IN ('UNK', 'Various', '-')` |
| `solutions.returned_refugees` etc. | `-` (null) | `try_cast(returned_refugees AS BIGINT) IS NOT NULL` (implicit via `SUM(try_cast(...))`) |

---

## Year coverage notes

| Table | Year range | Coverage notes |
|---|---|---|
| `asylum_applications` | 2000–2024 | Better after 2010. |
| `asylum_decisions` | 2000–2024 | Same as applications. |
| `solutions` | 1959–2024 | Very sparse historically. Resettlement reliable from ~1980, returns from ~1970. |
| `countries` | n/a | 232 rows. |
| `years` | 1951–2026 | 2025/2026 are placeholders. |

---

## Methodology surface (user-facing)

> Source: UNHCR Refugee Data Finder (`api.unhcr.org/population/v1/`),
> snapshot pulled 2026-05-06. Licensed under CC BY 4.0. Asylum
> applications/decisions and durable solutions are annual **flows** —
> events occurring during the year. A decision reached in 2023 may
> reflect an application filed in 2020–2022 (asylum backlogs are
> typically 1–3 years).

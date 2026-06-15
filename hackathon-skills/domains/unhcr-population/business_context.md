# UNHCR Population & Demographics — Business Context

> Table schemas, column meanings, metric formulas, and domain glossary for the
> stocks half of the UNHCR Refugee Data Finder. Read this BEFORE writing SQL.
> For flows (applications, decisions, durable solutions) see the
> `unhcr-asylum-flow` domain.

All tables live in **`workspace.hackathon`** on the hackathon-test workspace.
Row counts captured 2026-05-12 against the CSV snapshot pulled 2026-05-06.

---

## Domain glossary

Read this section first — UNHCR's legal vocabulary is exact and overlapping
terms have **different** meanings.

| Term | Definition | Key column / source |
|---|---|---|
| **Refugee** | Person granted refugee status under the 1951 Convention or under UNHCR's mandate. Year-end stock. | `population.refugees` |
| **Asylum-seeker** | Person whose claim for international protection is pending a final decision. Year-end stock. NOT the same as a refugee. | `population.asylum_seekers` |
| **IDP** (Internally Displaced Person) | Person displaced **inside their own country**. Not a refugee under international law. | `population.idps` or `idmc.total` |
| **Stateless** | Person not considered a national by any state. May or may not be displaced. | `population.stateless` |
| **OOC** (Other of Concern) | Mostly post-2017 "Venezuelans displaced abroad" + other ad-hoc categories. | `population.ooc` |
| **COO** (Country of Origin) | Where the person came from. | `coo_iso` |
| **COA** (Country of Asylum) | Where the person sought protection. For IDPs, equals COO. | `coa_iso` |
| **Forcibly displaced** | Headline aggregate. `refugees + asylum_seekers + idps + ooc`. UNHCR uses 123M+ for 2024. | derived |
| **People in international protection** | `refugees + asylum_seekers`. Excludes IDPs (not international). | derived |
| **Refugees abroad** | `population.refugees WHERE coo_iso <> coa_iso`. Distinguishes from internal displacement. | derived |

---

## Country-code dual system — the #1 footgun

UNHCR carries **two parallel 3-letter codes** per country. They overlap on
most strings but mean different countries for many:

| Column | System | Note |
|---|---|---|
| `coo` / `coa` | UNHCR internal | Use ONLY for raw inspection. Never join on these. |
| `coo_iso` / `coa_iso` | ISO 3166-1 alpha-3 | **Canonical join key.** |
| `coo_name` / `coa_name` | Display name | Stable; safe to surface to users. |

Known divergences:

| Internal `coo` | UNHCR meaning | ISO3 `coo_iso` |
|---|---|---|
| `SUD` | Sudan | `SDN` |
| `CHD` | Chad | `TCD` |
| `LBY` | Libya | `LBY` (same) |
| `AUS` | **Austria** (NOT Australia) | `AUT` |
| `ARE` | Egypt (NOT UAE) | `EGY` |
| `GFR` | Germany | `DEU` |

**Rule (R1):** Always join + group by `coo_iso` / `coa_iso`. Look up display
names from `countries.name` keyed on `iso`. See SKILL.md R1.

---

## Tables

### 1. `workspace.hackathon.population` — 132,603 rows

Annual end-year **stocks** of displaced populations by origin × asylum pair.
Years 1951–2024. This is the workhorse table for "how many displaced"
questions.

| Column | Type | Description |
|---|---|---|
| `year` | INT | Reporting year (1951–2024). |
| `coo_id` | INT | UNHCR internal numeric country-of-origin ID. |
| `coo_name` | STRING | Country of origin display name. |
| `coo` | STRING | UNHCR internal 3-letter code. **Don't join on this.** |
| `coo_iso` | STRING | ISO3 country-of-origin code. **Canonical join key.** |
| `coa_id` | INT | UNHCR internal numeric country-of-asylum ID. |
| `coa_name` | STRING | Country of asylum display name. |
| `coa` | STRING | UNHCR internal 3-letter code. **Don't join on this.** |
| `coa_iso` | STRING | ISO3 country-of-asylum code. **Canonical join key.** |
| `refugees` | INT | End-year refugee stock at the (origin, asylum) pair. |
| `asylum_seekers` | INT | End-year asylum-seeker stock at the pair. |
| `returned_refugees` | INT | Refugees who returned to origin in the year (carried on population for convenience — the canonical flow lives in `solutions`). |
| `idps` | INT | Internally displaced person stock. Non-zero only when `coo_iso = coa_iso`. |
| `returned_idps` | INT | IDPs who returned home in the year. |
| `stateless` | INT | Stateless person stock at the pair. |
| `ooc` | INT | "Others of Concern" stock at the pair. See R2 for VEN reclassification. |
| `oip` | STRING | "Other in need of int'l protection" — **stored as string with `-` as null sentinel.** |
| `hst` | INT | Internal host-status flag. Generally not user-surfaced. |

**Primary key:** `(year, coo, coa)`. For analytic queries, group by
`(year, coo_iso, coa_iso)`.

### 2. `workspace.hackathon.demographics` — 109,947 rows

Annual age-sex breakdown of `refugees + asylum_seekers` at the same
(origin, asylum) grain. Years 2001–2024.

Joins 1:1 to `population` on `(year, coo, coa)`. Note: `demographics` only
covers the **subset of host countries that report age-sex breakdowns**
(≈88M of ≈123M total displaced).

| Column | Type | Description |
|---|---|---|
| `year` | INT | Reporting year. |
| `coo_id`, `coo_name`, `coo`, `coo_iso` | mixed | Origin (same semantics as `population`). |
| `coa_id`, `coa_name`, `coa`, `coa_iso` | mixed | Asylum country. |
| `f_0_4`, `f_5_11`, `f_12_17`, `f_18_59`, `f_60` | INT | Female counts by age band. |
| `f_other` | INT | Female age unknown. |
| `f_total` | INT | All females. |
| `m_0_4`, `m_5_11`, `m_12_17`, `m_18_59`, `m_60` | INT | Male counts by age band. |
| `m_other` | INT | Male age unknown. |
| `m_total` | INT | All males. |
| `total` | INT | Grand total (should equal `f_total + m_total`). |

**Subjugating rule (R6):** Suppress or merge cells < 5 when the user query
combines (country × age-band × sex) at fine granularity. See SKILL.md R6.

### 3. `workspace.hackathon.idmc` — 881 rows

IDMC (Internal Displacement Monitoring Centre) IDP stocks. Aggregate by
country (origin); `coa_iso` typically equals `coo_iso` or is `'-'`. Years
1990–2024.

| Column | Type | Description |
|---|---|---|
| `year` | INT | Year. |
| `coo_id`, `coo_name`, `coo`, `coo_iso` | mixed | Origin country. |
| `coa_id` | **STRING** | Sentinel (often `'-'`) — note this is STRING in idmc only. |
| `coa_name`, `coa`, `coa_iso` | STRING | Often blank / `'-'` for country-aggregate rows. |
| `total` | INT | IDP stock count. |

**Don't sum with `population.idps`** (R4) — they overlap. Use `idmc` only
when explicitly asked, or when `population.idps` returns no row for a year
of interest.

### 4. `workspace.hackathon.countries` — 232 rows

Reference table for ISO3 → country name and metadata.

| Column | Type | Description |
|---|---|---|
| `0` | INT | Pandas index column carried from CSV — **ignore**. |
| `id` | INT | UNHCR internal numeric country ID. |
| `code` | STRING | UNHCR internal 3-letter code (joins to `population.coo`/`coa`). |
| `iso` | STRING | **ISO3 code.** Joins to `*_iso` columns. |
| `iso2` | STRING | ISO2 code. |
| `name` | STRING | **Canonical display name.** Use for user-facing output. |
| `nameOrigin` | STRING | Name as the country would call itself ("Deutschland"). |
| `nameLong`, `nameShort`, `nameFormal` | STRING | Naming variants. |
| `nationality` | STRING | Demonym ("German", "Sudanese"). |
| `majorArea`, `region` | STRING | UN geographic regions. |
| `nameFr`, `majorAreaFr`, `regionFr` | STRING | French equivalents. |

**Join pattern:** `JOIN workspace.hackathon.countries c ON c.iso = pop.coo_iso`.

### 5. `workspace.hackathon.years` — 76 rows

Reference list of valid year values (1951–2026 incl. placeholder rows for
2025–2026 with no data yet). One INT column: `year`.

---

## External reference tables (R16) — World Bank, for per-capita & GDP stories

The 8 UNHCR tables carry **no host-country population or GDP**, so per-capita
burden and the GDP-vs-burden scatter are impossible from the dump alone. Two
small **World Bank** reference tables (CC BY 4.0, ISO3-keyed) make those joins
possible. They are loaded once via `hackathon-orchestrator/deployment/load_reference_tables.py`
(source CSVs bundled at `deployment/ref/`). **Latest-available-year per country**
(NOT a year time-series) — join on `iso` only, surface `pop_year`/`gdp_year` for transparency.

### `workspace.hackathon.host_population` — ~193 rows

| Column | Type | Description |
|---|---|---|
| `iso` | STRING | ISO3 (World Bank `iso3`, renamed on load). Joins to `*_iso` / `countries.iso`. |
| `country` | STRING | World Bank country name (display only; prefer `countries.name`). |
| `population` | BIGINT | Total resident population (World Bank `SP.POP.TOTL`). |
| `pop_year` | INT | Year of the population figure (mostly 2024). |
| `source` | STRING | `"World Bank SP.POP.TOTL"`. |

### `workspace.hackathon.host_gdp` — ~190 rows

| Column | Type | Description |
|---|---|---|
| `iso` | STRING | ISO3 (renamed from `iso3` on load). |
| `country` | STRING | World Bank country name. |
| `gdp_pc_usd` | DOUBLE | GDP per capita, current US$ (World Bank `NY.GDP.PCAP.CD`). |
| `gdp_year` | INT | Year of the GDP figure (2023–2024). |
| `source` | STRING | `"World Bank NY.GDP.PCAP.CD"`. |

> **If these tables are absent**, per-capita / GDP stories CANNOT be computed.
> Fall back to absolute host leaderboards (Pattern 2 / 9) and tell the user the
> per-capita reference table needs to be loaded. Never fabricate populations/GDP.
> Methodology footer must add a second source line: "Host population & GDP:
> World Bank (SP.POP.TOTL, NY.GDP.PCAP.CD), CC BY 4.0."

---

## Key derived metrics (stock domain)

These are the canonical formulas. Never invent alternatives.

| Metric | Formula |
|---|---|
| **Forcibly displaced (UNHCR headline)** | `SUM(refugees) + SUM(asylum_seekers) + SUM(idps) + SUM(ooc)` from `population` |
| **People in international protection** | `SUM(refugees) + SUM(asylum_seekers)` |
| **Refugees abroad from country X** | `SUM(refugees) WHERE coo_iso = X AND coo_iso <> coa_iso` |
| **Total displaced from country X** | `SUM(refugees + asylum_seekers + idps + ooc) WHERE coo_iso = X` (origin scope, includes internally displaced) |
| **Top hosts of country X refugees** | `SUM(refugees) GROUP BY coa_iso WHERE coo_iso = X ORDER BY 2 DESC` |
| **Top origins for country Y** | `SUM(refugees) GROUP BY coo_iso WHERE coa_iso = Y ORDER BY 2 DESC` |
| **YoY change** | `(this_year - last_year) / NULLIF(last_year, 0)` (use `NULLIF` to avoid divide-by-zero) |

---

## Sentinel values to filter

| Where | Sentinel | Meaning | Filter pattern |
|---|---|---|---|
| `coo_iso`, `coa_iso` | `UNK` | Unknown country | `coo_iso NOT IN ('UNK', 'Various', '-')` |
| `coo_iso`, `coa_iso` | `Various` | Multiple countries | same |
| `coo_iso`, `coa_iso` | `-` | Missing | same |
| `population.oip` | `-` | Null in string column | `oip <> '-' AND oip IS NOT NULL` |
| `idmc.coa_iso` | `-` or empty | IDMC country-aggregate row | filter only if you want pairwise data |

---

## Year coverage notes

| Table | Year range | Coverage notes |
|---|---|---|
| `population` | 1951–2024 | Best coverage 1970+. IDPs spotty pre-2010, broad from 2015. |
| `demographics` | 2001–2024 | Subset of hosts only (≈88M of 123M displaced are covered). |
| `idmc` | 1990–2024 | Country-aggregate only. |
| `countries` | n/a | 232 rows (current as of 2024). |
| `years` | 1951–2026 | 2025/2026 are placeholders. |

---

## Methodology surface (user-facing)

When asked "where do these numbers come from?" or whenever a chart is
emitted, surface this paragraph (per data-journalism skill convention):

> Source: UNHCR Refugee Data Finder (`api.unhcr.org/population/v1/`),
> snapshot pulled 2026-05-06. Licensed under CC BY 4.0. All figures are
> end-year **stocks**. Demographic figures only cover the subset of host
> countries that report age-sex breakdowns (~88M of ~123M total
> displaced). Cells with fewer than 5 individuals suppressed per UNHCR
> statistical practice.

# UNHCR Population — SQL Patterns

> Proven query templates for stock questions. Adapt from these — do NOT
> write from scratch. All queries target tables in `workspace.hackathon`.
> Spark SQL syntax (`NULLIF`, `IS NOT NULL`, `LAG`).
>
> For flow patterns (applications, decisions, solutions) see the
> `unhcr-asylum-flow` domain.

---

## Preamble — three universal rules

**P1.** Always join on ISO3, never on UNHCR internal codes. (Rule R1.)
**P2.** Always filter sentinel rows from leaderboards (`UNK`, `Various`, `-`).
**P3.** Use country `name` (from `countries`) in user-facing output, not ISO3.

---

## Pattern 1 — Refugees by origin, single year, with country names

User: "How many refugees from Sudan in 2024?"

```sql
SELECT
  c.name AS origin_country,
  SUM(p.refugees) AS refugees,
  SUM(p.asylum_seekers) AS asylum_seekers,
  SUM(p.refugees) + SUM(p.asylum_seekers) AS people_in_intl_protection
FROM workspace.hackathon.population p
JOIN workspace.hackathon.countries c ON c.iso = p.coo_iso
WHERE p.coo_iso = 'SDN'
  AND p.year = 2024
  AND p.coo_iso <> p.coa_iso           -- exclude internally-displaced rows
GROUP BY c.name;
```

Substitution: change `'SDN'` to any ISO3. For "Sudan" the canonical ISO3 is
`SDN` (NOT `SUD`, which is UNHCR-internal). When user types a country name,
look it up first:

```sql
-- ISO3 lookup from user-typed name
SELECT iso, name FROM workspace.hackathon.countries
WHERE name ILIKE '%sudan%' OR nameShort ILIKE '%sudan%';
```

---

## Pattern 2 — Top N hosts of refugees from country X

User: "Top 5 host countries for Sudanese refugees in 2024."

```sql
SELECT
  c.name AS host_country,
  SUM(p.refugees) AS refugees
FROM workspace.hackathon.population p
JOIN workspace.hackathon.countries c ON c.iso = p.coa_iso
WHERE p.coo_iso = 'SDN'
  AND p.year = 2024
  AND p.coa_iso NOT IN ('UNK', 'Various', '-')   -- R8
  AND p.coo_iso <> p.coa_iso                     -- exclude IDPs
GROUP BY c.name
ORDER BY refugees DESC
LIMIT 5;
```

Chart shape: horizontal bar, country on Y-axis.

---

## Pattern 3 — Multi-year trend for one country

User: "Refugees from Sudan over the last 10 years."

```sql
SELECT
  year,
  SUM(refugees) AS refugees,
  SUM(asylum_seekers) AS asylum_seekers,
  SUM(idps) AS idps,
  SUM(ooc) AS ooc,
  SUM(refugees + asylum_seekers + idps + ooc) AS forcibly_displaced
FROM workspace.hackathon.population
WHERE coo_iso = 'SDN'
  AND year BETWEEN (SELECT MAX(year) - 9 FROM workspace.hackathon.population)
              AND (SELECT MAX(year) FROM workspace.hackathon.population)
GROUP BY year
ORDER BY year;
```

Chart shape: line or stacked area.

---

## Pattern 4 — Origin × year heatmap (top-N origins)

User: "Which crises have spiked when over the last decade?"

```sql
WITH top_origins AS (
  SELECT coo_iso
  FROM workspace.hackathon.population
  WHERE year = (SELECT MAX(year) FROM workspace.hackathon.population)
    AND coo_iso NOT IN ('UNK', 'Various', '-')
  GROUP BY coo_iso
  ORDER BY SUM(refugees + asylum_seekers + idps + ooc) DESC
  LIMIT 15
)
SELECT
  c.name AS origin,
  p.year,
  SUM(p.refugees + p.asylum_seekers + p.idps + p.ooc) AS forcibly_displaced
FROM workspace.hackathon.population p
JOIN top_origins t ON p.coo_iso = t.coo_iso
JOIN workspace.hackathon.countries c ON c.iso = p.coo_iso
WHERE p.year BETWEEN 2014 AND (SELECT MAX(year) FROM workspace.hackathon.population)
GROUP BY c.name, p.year;
```

Chart shape: heatmap, origin on Y, year on X, color = log(forcibly_displaced).

---

## Pattern 5 — Demographic breakdown with cell suppression (R6)

User: "Age and sex breakdown for refugees from Syria in Germany, 2024."

```sql
SELECT
  CASE
    WHEN f_0_4 + m_0_4 < 5 THEN NULL                  -- suppress
    ELSE f_0_4 + m_0_4
  END AS age_0_4,
  CASE WHEN f_5_11 + m_5_11 < 5 THEN NULL ELSE f_5_11 + m_5_11 END AS age_5_11,
  CASE WHEN f_12_17 + m_12_17 < 5 THEN NULL ELSE f_12_17 + m_12_17 END AS age_12_17,
  CASE WHEN f_18_59 + m_18_59 < 5 THEN NULL ELSE f_18_59 + m_18_59 END AS age_18_59,
  CASE WHEN f_60 + m_60 < 5 THEN NULL ELSE f_60 + m_60 END AS age_60_plus,
  f_total + m_total AS total
FROM workspace.hackathon.demographics
WHERE coo_iso = 'SYR' AND coa_iso = 'DEU' AND year = 2024;
```

Surface in the answer footer:
"Cells with fewer than 5 individuals suppressed per UNHCR statistical
practice."

For a male-vs-female pivot (apply `< 5` suppression in the calling code when
slicing finer than country × all-ages):

```sql
SELECT 'female' AS sex,
       SUM(f_0_4) AS age_0_4, SUM(f_5_11) AS age_5_11, SUM(f_12_17) AS age_12_17,
       SUM(f_18_59) AS age_18_59, SUM(f_60) AS age_60_plus, SUM(f_total) AS total
FROM workspace.hackathon.demographics
WHERE coo_iso = 'SYR' AND year = 2024
UNION ALL
SELECT 'male', SUM(m_0_4), SUM(m_5_11), SUM(m_12_17),
       SUM(m_18_59), SUM(m_60), SUM(m_total)
FROM workspace.hackathon.demographics
WHERE coo_iso = 'SYR' AND year = 2024;
```

---

## Pattern 6 — Compare two countries side-by-side

User: "Compare Sudan to Syria's forced-displacement burden in 2024."

```sql
SELECT
  c.name AS origin,
  SUM(p.refugees)                              AS refugees,
  SUM(p.asylum_seekers)                        AS asylum_seekers,
  SUM(p.idps)                                  AS idps,
  SUM(p.ooc)                                   AS ooc,
  SUM(p.refugees + p.asylum_seekers + p.idps + p.ooc) AS forcibly_displaced
FROM workspace.hackathon.population p
JOIN workspace.hackathon.countries c ON c.iso = p.coo_iso
WHERE p.coo_iso IN ('SDN', 'SYR')
  AND p.year = 2024
GROUP BY c.name
ORDER BY forcibly_displaced DESC;
```

The newsroom fact-checker angle: Sudan exceeds Syria on **total displaced**
(because of IDPs) but Syria still has more **refugees abroad**.

---

## Pattern 7 — YoY change for any stock metric

```sql
WITH yearly AS (
  SELECT year, SUM(refugees) AS refugees
  FROM workspace.hackathon.population
  WHERE coo_iso = 'SDN'
  GROUP BY year
)
SELECT
  year,
  refugees,
  LAG(refugees) OVER (ORDER BY year)                                AS prev_year_refugees,
  refugees - LAG(refugees) OVER (ORDER BY year)                      AS yoy_change,
  ROUND(
    (refugees - LAG(refugees) OVER (ORDER BY year)) * 100.0
    / NULLIF(LAG(refugees) OVER (ORDER BY year), 0),
    2
  )                                                                  AS yoy_pct
FROM yearly
ORDER BY year;
```

---

## Pattern 8 — IDP source disambiguation (R4)

User: "How many IDPs are there in Sudan?" — prefer `population.idps`:

```sql
SELECT
  year,
  SUM(idps) AS idps
FROM workspace.hackathon.population
WHERE coo_iso = 'SDN' AND coa_iso = 'SDN'
  AND year >= 2015                              -- coverage threshold
GROUP BY year
ORDER BY year;
```

ONLY if explicitly asked for IDMC, or if `population.idps` returns no row:

```sql
SELECT year, total AS idps
FROM workspace.hackathon.idmc
WHERE coo_iso = 'SDN'
ORDER BY year;
```

**NEVER sum the two** (R4).

---

## Pattern 9 — Newsroom fact-check style verification

User: "Lebanon hosts 1 in 6 of the world's refugees."

```sql
WITH world AS (
  SELECT SUM(refugees) AS world_refugees
  FROM workspace.hackathon.population
  WHERE year = 2024
    AND coo_iso <> coa_iso
    AND coo_iso NOT IN ('UNK', 'Various', '-')
    AND coa_iso NOT IN ('UNK', 'Various', '-')
),
lebanon AS (
  SELECT SUM(refugees) AS lebanon_refugees
  FROM workspace.hackathon.population
  WHERE year = 2024
    AND coa_iso = 'LBN'
    AND coo_iso <> coa_iso
)
SELECT
  world.world_refugees,
  lebanon.lebanon_refugees,
  ROUND(lebanon.lebanon_refugees * 100.0 / NULLIF(world.world_refugees, 0), 2) AS lebanon_share_pct,
  ROUND(world.world_refugees / NULLIF(lebanon.lebanon_refugees, 0), 1) AS one_in_n
FROM world CROSS JOIN lebanon;
```

The EDA confirms: end-2024 Lebanon ≈ 1 in 41 of the world's refugees
(~2.4%), not 1 in 6.

---

## Pattern 10 — Crisis dashboard for one country (headline demo)

User: "Brief me on Sudan."

Returns 4 tiles in one round-trip (one SELECT per metric, joined in
`query_stored_dfs` afterwards):

**KPI 1 — Total displaced from country**
```sql
SELECT
  SUM(refugees)                                AS refugees_abroad,
  SUM(asylum_seekers)                          AS asylum_seekers_abroad,
  SUM(idps)                                    AS idps,
  SUM(ooc)                                     AS ooc,
  SUM(refugees + asylum_seekers + idps + ooc)  AS forcibly_displaced
FROM workspace.hackathon.population
WHERE coo_iso = 'SDN' AND year = (SELECT MAX(year) FROM workspace.hackathon.population);
```

**KPI 2 — YoY change**
```sql
WITH t AS (
  SELECT year, SUM(refugees + asylum_seekers + idps + ooc) AS forcibly_displaced
  FROM workspace.hackathon.population
  WHERE coo_iso = 'SDN' AND year IN (
    (SELECT MAX(year)   FROM workspace.hackathon.population),
    (SELECT MAX(year)-1 FROM workspace.hackathon.population)
  )
  GROUP BY year
)
SELECT MAX(CASE WHEN year = (SELECT MAX(year) FROM workspace.hackathon.population) THEN forcibly_displaced END)   AS current_yr,
       MAX(CASE WHEN year = (SELECT MAX(year)-1 FROM workspace.hackathon.population) THEN forcibly_displaced END) AS prior_yr
FROM t;
```

**Trend — line chart over time** (use Pattern 3 unchanged).

**Top hosts** (use Pattern 2 unchanged).

Compose in `query_stored_dfs` or `run_python_code`, render as dashboard.

---

## Story patterns (S-series) — concentration, burden, corridors, demographics

> These feed the **data-story infographics** (Lorenz/Gini, per-capita burden,
> GDP-burden scatter, Sankey corridors, child-share). They reproduce the
> validated `findings.json` numbers. S2/S6 need the **external reference tables**
> documented in `business_context.md` → "External reference tables (R16)";
> if those tables are absent, fall back to an **absolute** host leaderboard and say so.

### S1 — Refugee concentration (Lorenz curve + Gini input)

User: "How concentrated is the world's refugee burden?"

Return every origin→host refugee pair with its cumulative share (sorted ascending),
so Python can build the Lorenz curve + Gini. (Gini = 0.977 across ~4,745 pairs.)

```sql
WITH pairs AS (
  SELECT p.coo_iso, p.coa_iso, SUM(p.refugees) AS refugees
  FROM workspace.hackathon.population p
  WHERE p.year = 2024
    AND p.coo_iso <> p.coa_iso                              -- refugees only, not IDPs
    AND p.coo_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
    AND p.coa_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
  GROUP BY p.coo_iso, p.coa_iso
  HAVING SUM(p.refugees) > 0
)
SELECT
  refugees,
  ROW_NUMBER() OVER (ORDER BY refugees) AS rank_asc,
  COUNT(*)     OVER ()                  AS n_pairs,
  SUM(refugees) OVER (ORDER BY refugees ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 1.0
    / NULLIF(SUM(refugees) OVER (), 0)  AS cum_share
FROM pairs
ORDER BY refugees;
```

Python: Gini = 1 − Σ(xᵢ)(2·cum_share_to_i − share_i) … or the standard sorted formula.
Chart: **Lorenz curve with Gini** (diagonal = equality; the bowed line is the inequality).

### S2 — Per-capita burden (refugees per 1,000 residents)

User: "Which countries carry the heaviest refugee burden relative to their size?"

Needs `host_population` reference (R16). Lebanon ≈ 132.9 / 1,000; Chad ≈ 63.4.

```sql
WITH hosted AS (
  SELECT p.coa_iso, SUM(p.refugees) AS hosted
  FROM workspace.hackathon.population p
  WHERE p.year = 2024
    AND p.coo_iso <> p.coa_iso
    AND p.coa_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
  GROUP BY p.coa_iso
)
SELECT
  c.name AS host, h.hosted, r.population AS residents, r.pop_year,
  ROUND(h.hosted * 1000.0 / NULLIF(r.population, 0), 1) AS refugees_per_1000
FROM hosted h
JOIN workspace.hackathon.host_population r ON r.iso = h.coa_iso   -- ref is latest-year-per-country
JOIN workspace.hackathon.countries c       ON c.iso = h.coa_iso
WHERE h.hosted >= 10000                      -- ignore tiny absolute hosts for a per-capita ranking
ORDER BY refugees_per_1000 DESC
LIMIT 20;
```

Chart: **ranked bar with highlight** (per-capita reframes the "generous nations" story).
> ⚠ If `host_population` is missing, this errors. Fall back to the absolute Pattern 2/9
> leaderboard and tell the user the per-capita view needs the reference table loaded.

### S3 — Within-region containment share

User: "How much displacement stays within its own region?"

Story: `within_region_share ≈ 0.848` — most refugees stay in a neighbouring country.

```sql
SELECT
  ROUND(SUM(CASE WHEN co.region = ca.region THEN p.refugees ELSE 0 END) * 100.0
        / NULLIF(SUM(p.refugees), 0), 1) AS within_region_pct
FROM workspace.hackathon.population p
JOIN workspace.hackathon.countries co ON co.iso = p.coo_iso
JOIN workspace.hackathon.countries ca ON ca.iso = p.coa_iso
WHERE p.year = 2024
  AND p.coo_iso <> p.coa_iso
  AND p.coo_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
  AND p.coa_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','');
```

### S4 — Origin → host corridor pairs (Sankey)

User: "Show the biggest refugee corridors."

```sql
SELECT
  co.name AS origin, ca.name AS host, SUM(p.refugees) AS refugees
FROM workspace.hackathon.population p
JOIN workspace.hackathon.countries co ON co.iso = p.coo_iso
JOIN workspace.hackathon.countries ca ON ca.iso = p.coa_iso
WHERE p.year = 2024
  AND p.coo_iso <> p.coa_iso                                  -- drop self-loops (IDPs)
  AND p.coo_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
  AND p.coa_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
GROUP BY co.name, ca.name
HAVING SUM(p.refugees) > 0
ORDER BY refugees DESC
LIMIT 25;
```

Chart: **Sankey corridors** (origin nodes left, host nodes right, flow = refugees).

### S5 — Child share of known age (demographics)

User: "What share of the displaced are children?"

Story: `child_share_known_age ≈ 0.448`; children ≈ 35.98M.

```sql
SELECT
  year,
  SUM(f_0_4 + f_5_11 + f_12_17 + m_0_4 + m_5_11 + m_12_17)                       AS children,
  SUM(f_0_4 + f_5_11 + f_12_17 + f_18_59 + f_60
    + m_0_4 + m_5_11 + m_12_17 + m_18_59 + m_60)                                 AS known_age,
  ROUND(SUM(f_0_4 + f_5_11 + f_12_17 + m_0_4 + m_5_11 + m_12_17) * 100.0
        / NULLIF(SUM(f_0_4 + f_5_11 + f_12_17 + f_18_59 + f_60
                   + m_0_4 + m_5_11 + m_12_17 + m_18_59 + m_60), 0), 1)          AS child_share_pct
FROM workspace.hackathon.demographics
WHERE year BETWEEN 2014 AND 2024
GROUP BY year
ORDER BY year;
```

> Excludes `*_other`/`*_total` from the denominator (age unknown). Surface "of known age".

### S6 — GDP per capita vs burden (the "significant ≠ meaningful" scatter)

Needs both `host_population` and `host_gdp` (R16). Story: r ≈ 0.22, R² ≈ 0.05 (n ≈ 82).

```sql
WITH burden AS (   -- reuse S2's per-capita computation
  SELECT h.coa_iso AS iso, h.hosted,
         h.hosted * 1000.0 / NULLIF(r.population, 0) AS refugees_per_1000
  FROM (SELECT coa_iso, SUM(refugees) AS hosted
        FROM workspace.hackathon.population
        WHERE year = 2024 AND coo_iso <> coa_iso
          AND coa_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
        GROUP BY coa_iso) h
  JOIN workspace.hackathon.host_population r ON r.iso = h.coa_iso
)
SELECT
  c.name AS host, c.region, b.hosted, b.refugees_per_1000,
  g.gdp_pc_usd AS gdp_per_capita_usd, g.gdp_year
FROM burden b
JOIN workspace.hackathon.host_gdp g  ON g.iso = b.iso
JOIN workspace.hackathon.countries c ON c.iso = b.iso
WHERE b.hosted >= 10000 AND g.gdp_pc_usd IS NOT NULL
ORDER BY b.refugees_per_1000 DESC;
```

Chart: **log–log bubble scatter** (x = GDP/cap, y = refugees/1,000, bubble = hosted,
colour = region) + OLS fit. Honest finding: burden tracks geography, not wealth.

---

## Anti-patterns — do NOT do these

❌ **Compute per-capita burden without `host_population`** — the reference table must be
   loaded (R16). If it isn't, use absolute leaderboards and say the per-capita view is unavailable.
❌ **Sum `population.idps` and `idmc.total` together** — double counts.
❌ **Group by `coo`/`coa`** — UNHCR-internal codes; will mis-attribute
   countries (`AUS` is Austria, not Australia).
❌ **Show "Unknown" in a top-N leaderboard** — sentinel rows in `coo_iso`.
   Filter R8.
❌ **Use `population.refugees` as flow** — it's a year-end stock. Flows
   live in the asylum-flow domain.
❌ **Single-row chart** — if SUM returns one number, answer in text. Don't
   call `render_chart`.
❌ **Surface user's exact words in the country lookup** — always
   ISO3-normalise first.

---

## Reference queries for validation

After deploying the orchestrator, these queries should return the EDA's
truth values. Use them to validate the agent's first-week answers:

| Query | Expected (2024) |
|---|---|
| Top origin by forcibly_displaced | Sudan ≈ 14.34M |
| Top host of Sudan refugees | Chad ≈ 1.11M |
| Total Syria refugees abroad | ≈ 5.95M |
| Total Sudan refugees abroad | ≈ 2.09M |
| Total displaced from Syria | ≈ 13.53M |
| Total displaced from Sudan | ≈ 14.34M |
| Lebanon share of world refugees | ≈ 2.4% (1 in 41) |
| Venezuelan OOC | ≈ 3.4M+ (post-reclassification) |

Verified by hackathon/notes/eda/findings.md against the CSV snapshot.

# UNHCR Asylum & Solutions — SQL Patterns

> Proven query templates for flow questions. Adapt from these — do NOT
> write from scratch. All queries target tables in `workspace.hackathon`.
> Spark SQL syntax (`try_cast`, `NULLIF`).
>
> For stock patterns (population, demographics, IDMC) see the
> `unhcr-population` domain.

---

## Preamble — four universal rules

**P1.** Always join on ISO3, never on UNHCR internal codes. (Rule R1.)
**P2.** Always filter sentinel rows from leaderboards (`UNK`, `Various`, `-`).
**P3.** Always `try_cast(... AS BIGINT)` `solutions` string columns before SUM/AVG (R7).
**P4.** Always surface `dec_total` alongside a recognition rate — a 100%
rate from 1 decision is not the same as 80% from 10,000.

---

## Pattern 1 — Asylum applications filed in a country, single year

User: "How many asylum applications did Germany receive in 2023?"

```sql
SELECT
  SUM(applied) AS applications,
  COUNT(DISTINCT coo_iso) AS distinct_origins
FROM workspace.hackathon.asylum_applications
WHERE coa_iso = 'DEU'
  AND year = 2023
  AND coo_iso NOT IN ('UNK', 'Various', '-');
```

Variant — by origin (where did applicants come from?):

```sql
SELECT
  c.name AS origin,
  SUM(aa.applied) AS applications
FROM workspace.hackathon.asylum_applications aa
JOIN workspace.hackathon.countries c ON c.iso = aa.coo_iso
WHERE aa.coa_iso = 'DEU'
  AND aa.year = 2023
  AND aa.coo_iso NOT IN ('UNK', 'Various', '-')
GROUP BY c.name
ORDER BY applications DESC
LIMIT 10;
```

---

## Pattern 2 — Recognition rate, single country, single year

User: "What's the asylum recognition rate in Germany for 2023?"

```sql
SELECT
  procedure_type,
  SUM(dec_recognized)  AS recognized,
  SUM(dec_other)       AS other_protected,
  SUM(dec_rejected)    AS rejected,
  SUM(dec_closed)      AS closed,
  SUM(dec_total)       AS total_decisions,
  ROUND(SUM(dec_recognized) * 100.0 / NULLIF(SUM(dec_total), 0), 2)                   AS recognition_rate_pct,
  ROUND(SUM(dec_recognized + dec_other) * 100.0 / NULLIF(SUM(dec_total), 0), 2)       AS protection_rate_pct,
  ROUND(SUM(dec_rejected) * 100.0 / NULLIF(SUM(dec_total), 0), 2)                     AS rejection_rate_pct
FROM workspace.hackathon.asylum_decisions
WHERE coa_iso = 'DEU'
  AND year = 2023
GROUP BY procedure_type
ORDER BY total_decisions DESC;
```

R12 note: split by `procedure_type` so the user sees G vs U.
R13 note: closures (`dec_closed`) are NOT rejections.

---

## Pattern 3 — Recognition rate by origin (where do recognised refugees come from?)

User: "Which countries' asylum applicants get recognised in Germany?"

```sql
SELECT
  c.name AS origin,
  SUM(ad.dec_recognized) AS recognized,
  SUM(ad.dec_total)      AS total_decisions,
  ROUND(SUM(ad.dec_recognized) * 100.0 / NULLIF(SUM(ad.dec_total), 0), 2) AS recognition_rate_pct
FROM workspace.hackathon.asylum_decisions ad
JOIN workspace.hackathon.countries c ON c.iso = ad.coo_iso
WHERE ad.coa_iso = 'DEU'
  AND ad.year = 2023
  AND ad.coo_iso NOT IN ('UNK', 'Various', '-')
GROUP BY c.name
HAVING SUM(ad.dec_total) >= 100         -- suppress tiny denominators (P4)
ORDER BY total_decisions DESC
LIMIT 15;
```

---

## Pattern 4 — Durable solutions with cast preamble (R7)

User: "How many refugees were resettled globally in 2023?"

```sql
SELECT
  SUM(try_cast(resettlement      AS BIGINT)) AS resettled,
  SUM(try_cast(naturalisation    AS BIGINT)) AS naturalised,
  SUM(try_cast(returned_refugees AS BIGINT)) AS returned_refugees,
  SUM(try_cast(returned_idps     AS BIGINT)) AS returned_idps
FROM workspace.hackathon.solutions
WHERE year = 2023
  AND coo_iso NOT IN ('UNK', 'Various', '-');
```

`try_cast` returns NULL for invalid casts (including `'-'`); `SUM` ignores
nulls. Cleaner than `WHERE column <> '-'` chains.

Variant — top resettlement destinations:

```sql
SELECT
  c.name AS resettlement_destination,
  SUM(try_cast(s.resettlement AS BIGINT)) AS resettled
FROM workspace.hackathon.solutions s
JOIN workspace.hackathon.countries c ON c.iso = s.coa_iso
WHERE s.year = 2023
  AND s.coa_iso NOT IN ('UNK', 'Various', '-')
GROUP BY c.name
HAVING SUM(try_cast(s.resettlement AS BIGINT)) > 0
ORDER BY resettled DESC NULLS LAST
LIMIT 10;
```

---

## Pattern 5 — Application flow + decision merge (with R11 caveat)

User: "How many Afghan asylum applications were filed in the EU in 2023,
and how many were recognised?"

```sql
WITH eu_iso AS (
  SELECT iso FROM workspace.hackathon.countries
  WHERE region IN ('Europe')                  -- broad approximation; tighten if needed
),
applied AS (
  SELECT SUM(applied) AS applied
  FROM workspace.hackathon.asylum_applications a
  JOIN eu_iso e ON a.coa_iso = e.iso
  WHERE a.coo_iso = 'AFG' AND a.year = 2023
),
decisions AS (
  SELECT
    SUM(dec_recognized) AS recognized,
    SUM(dec_total)      AS total_decisions
  FROM workspace.hackathon.asylum_decisions d
  JOIN eu_iso e ON d.coa_iso = e.iso
  WHERE d.coo_iso = 'AFG' AND d.year = 2023
)
SELECT
  applied.applied,
  decisions.recognized,
  decisions.total_decisions,
  ROUND(decisions.recognized * 100.0 / NULLIF(decisions.total_decisions, 0), 2)
    AS recognition_rate_pct
FROM applied CROSS JOIN decisions;
```

**R11 caveat to surface in the user answer:**
> Note: 2023 decisions and 2023 applications are not directly related —
> the recognised decisions come from applications filed in earlier years
> (typical asylum backlogs run 1–3 years).

---

## Pattern 6 — Trend: recognition rate over time

User: "Has the recognition rate for Syrian asylum-seekers in Germany
changed over time?"

```sql
SELECT
  year,
  SUM(dec_recognized) AS recognized,
  SUM(dec_total)      AS total_decisions,
  ROUND(SUM(dec_recognized) * 100.0 / NULLIF(SUM(dec_total), 0), 2) AS recognition_rate_pct
FROM workspace.hackathon.asylum_decisions
WHERE coa_iso = 'DEU'
  AND coo_iso = 'SYR'
GROUP BY year
HAVING SUM(dec_total) >= 100
ORDER BY year;
```

Chart shape: line, year on X, recognition_rate_pct on Y. Annotate the
2015-2016 Syria-crisis peak.

---

## Pattern 7 — Procedure type comparison

User: "How does government RSD compare to UNHCR RSD in <country> for 2023?"

```sql
SELECT
  procedure_type,
  SUM(dec_total)      AS total_decisions,
  SUM(dec_recognized) AS recognized,
  ROUND(SUM(dec_recognized) * 100.0 / NULLIF(SUM(dec_total), 0), 2) AS recognition_rate_pct
FROM workspace.hackathon.asylum_decisions
WHERE coa_iso = 'KEN'   -- Kenya: a country with both G and U decisions
  AND year = 2023
GROUP BY procedure_type
ORDER BY procedure_type;
```

R12 note: surface the breakdown when both are present.

---

## Pattern 8 — Top resettlement origins (where do refugees most often get resettled FROM?)

User: "Top 10 origins of refugees resettled in 2023."

```sql
SELECT
  c.name AS origin,
  SUM(try_cast(s.resettlement AS BIGINT)) AS resettled
FROM workspace.hackathon.solutions s
JOIN workspace.hackathon.countries c ON c.iso = s.coo_iso
WHERE s.year = 2023
  AND s.coo_iso NOT IN ('UNK', 'Various', '-')
GROUP BY c.name
HAVING SUM(try_cast(s.resettlement AS BIGINT)) > 0
ORDER BY resettled DESC NULLS LAST
LIMIT 10;
```

---

## Pattern 9 — Decision outcome composition (stacked bar)

User: "Breakdown of asylum decision outcomes in Germany 2023."

```sql
SELECT
  SUM(dec_recognized) AS recognized,
  SUM(dec_other)      AS complementary,
  SUM(dec_rejected)   AS rejected,
  SUM(dec_closed)     AS closed
FROM workspace.hackathon.asylum_decisions
WHERE coa_iso = 'DEU' AND year = 2023;
```

Chart shape: 100% stacked horizontal bar (4 segments), absolute values
overlaid as labels. R13 — label `closed` distinctly so users don't read
it as rejection.

---

## Pattern 10 — Application trend over time, multi-origin

User: "Top 5 origins of asylum applications in the EU, year by year
2015-2024."

```sql
WITH eu_iso AS (
  SELECT iso FROM workspace.hackathon.countries WHERE region IN ('Europe')
),
top5 AS (
  SELECT a.coo_iso
  FROM workspace.hackathon.asylum_applications a
  JOIN eu_iso e ON a.coa_iso = e.iso
  WHERE a.year BETWEEN 2015 AND 2024
    AND a.coo_iso NOT IN ('UNK', 'Various', '-')
  GROUP BY a.coo_iso
  ORDER BY SUM(a.applied) DESC
  LIMIT 5
)
SELECT
  a.year,
  c.name AS origin,
  SUM(a.applied) AS applications
FROM workspace.hackathon.asylum_applications a
JOIN top5 t ON a.coo_iso = t.coo_iso
JOIN eu_iso e ON a.coa_iso = e.iso
JOIN workspace.hackathon.countries c ON c.iso = a.coo_iso
WHERE a.year BETWEEN 2015 AND 2024
GROUP BY a.year, c.name
ORDER BY a.year, applications DESC;
```

Chart shape: multi-line, year on X, applications on Y, color = origin.

---

## Story patterns (S-series) — the asylum-lottery / matrix / regression family

> These reproduce the **validated infographic numbers**. They differ from P1–P10
> in three ways: (1) **TRR** denominator (closures excluded), (2) the **FI + G + P**
> cohort, (3) the **Europe allow-list** (not `region IN ('Europe')`). See
> `business_context.md` → "Fair cross-country comparison cohort (R14)". Every S-pattern
> opens with the same `europe` CTE; copy it verbatim.

```sql
-- Shared CTE for every S-pattern — EU-27 + EFTA + UK (30 ISO3 + 2 micro = 32).
WITH europe(iso) AS (VALUES
  ('AUT'),('BEL'),('BGR'),('HRV'),('CYP'),('CZE'),('DNK'),('EST'),('FIN'),('FRA'),
  ('DEU'),('GRC'),('HUN'),('IRL'),('ITA'),('LVA'),('LTU'),('LUX'),('MLT'),('NLD'),
  ('POL'),('PRT'),('ROU'),('SVK'),('SVN'),('ESP'),('SWE'),('ISL'),('NOR'),('CHE'),
  ('GBR'),('LIE'))
```

### S1 — TRR by destination ("the asylum lottery"): one origin, many states

User: "How differently do European countries treat Afghan asylum-seekers?"

```sql
WITH europe(iso) AS (VALUES
  ('AUT'),('BEL'),('BGR'),('HRV'),('CYP'),('CZE'),('DNK'),('EST'),('FIN'),('FRA'),
  ('DEU'),('GRC'),('HUN'),('IRL'),('ITA'),('LVA'),('LTU'),('LUX'),('MLT'),('NLD'),
  ('POL'),('PRT'),('ROU'),('SVK'),('SVN'),('ESP'),('SWE'),('ISL'),('NOR'),('CHE'),
  ('GBR'),('LIE'))
SELECT
  c.name AS destination,
  SUM(d.dec_recognized + d.dec_other)                                   AS protected,
  SUM(d.dec_recognized + d.dec_other + d.dec_rejected)                  AS substantive,
  ROUND(SUM(d.dec_recognized + d.dec_other) * 100.0
        / NULLIF(SUM(d.dec_recognized + d.dec_other + d.dec_rejected), 0), 1) AS trr_pct
FROM workspace.hackathon.asylum_decisions d
JOIN europe e ON d.coa_iso = e.iso
JOIN workspace.hackathon.countries c ON c.iso = d.coa_iso
WHERE d.coo_iso = 'AFG'
  AND d.year = 2023
  AND d.dec_level = 'FI'            -- first instance (NOT 'F')
  AND d.procedure_type = 'G'        -- government-led RSD only
  AND d.dec_pc = 'P'                -- persons
GROUP BY c.name
HAVING SUM(d.dec_recognized + d.dec_other + d.dec_rejected) >= 300   -- R15 cell suppression
ORDER BY trr_pct DESC;
```

Chart: **ranked bar with highlight** (Germany ~96% vs Sweden ~40%) — or a **forest/dot-plot
with CI whiskers** if you also compute Wilson intervals in Python. Headline cohort
n ≈ 472,165 across ~17 surviving destinations.

### S2 — Origin × destination recognition matrix (the lottery as texture)

User: "Show recognition rates for the top origins across European destinations."

```sql
WITH europe(iso) AS (VALUES /* …same 32 rows as above… */
  ('AUT'),('BEL'),('BGR'),('HRV'),('CYP'),('CZE'),('DNK'),('EST'),('FIN'),('FRA'),
  ('DEU'),('GRC'),('HUN'),('IRL'),('ITA'),('LVA'),('LTU'),('LUX'),('MLT'),('NLD'),
  ('POL'),('PRT'),('ROU'),('SVK'),('SVN'),('ESP'),('SWE'),('ISL'),('NOR'),('CHE'),
  ('GBR'),('LIE')),
top_origins AS (
  SELECT d.coo_iso
  FROM workspace.hackathon.asylum_decisions d
  JOIN europe e ON d.coa_iso = e.iso
  WHERE d.year = 2023 AND d.dec_level = 'FI' AND d.procedure_type = 'G' AND d.dec_pc = 'P'
    AND d.coo_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
  GROUP BY d.coo_iso
  ORDER BY SUM(d.dec_recognized + d.dec_other + d.dec_rejected) DESC
  LIMIT 12
)
SELECT
  co.name AS origin, cd.name AS destination,
  SUM(d.dec_recognized + d.dec_other + d.dec_rejected) AS substantive,
  ROUND(SUM(d.dec_recognized + d.dec_other) * 100.0
        / NULLIF(SUM(d.dec_recognized + d.dec_other + d.dec_rejected), 0), 1) AS trr_pct
FROM workspace.hackathon.asylum_decisions d
JOIN europe e        ON d.coa_iso = e.iso
JOIN top_origins t   ON d.coo_iso = t.coo_iso
JOIN workspace.hackathon.countries co ON co.iso = d.coo_iso
JOIN workspace.hackathon.countries cd ON cd.iso = d.coa_iso
WHERE d.year = 2023 AND d.dec_level = 'FI' AND d.procedure_type = 'G' AND d.dec_pc = 'P'
GROUP BY co.name, cd.name
HAVING SUM(d.dec_recognized + d.dec_other + d.dec_rejected) >= 300   -- R15: suppress thin cells
ORDER BY origin, destination;
```

Chart: **origin×destination diverging heatmap** (% printed in each cell; colour secondary
to the number — Cleveland–McGill). Story: Venezuelans 5.5% → 100% by destination.

### S3 — Origin-standardized TRR + Simpson's rank reversal

User: "Are some countries only 'generous' because of who applies there?"

Compute two ranks per destination: (a) **raw** pooled TRR, and (b) a TRR **standardized**
to a fixed origin mix (so caseload composition can't flatter a state). When the ranks
cross, that's Simpson's paradox — surface it.

```sql
WITH europe(iso) AS (VALUES /* …same 32 rows… */ ('DEU'),('SWE'),('ITA'),('GRC'),('FRA') /* + rest */),
cell AS (   -- per (destination, origin) cohort cell
  SELECT d.coa_iso AS dest, d.coo_iso AS orig,
         SUM(d.dec_recognized + d.dec_other)                  AS protected,
         SUM(d.dec_recognized + d.dec_other + d.dec_rejected) AS substantive
  FROM workspace.hackathon.asylum_decisions d
  JOIN europe e ON d.coa_iso = e.iso
  WHERE d.year = 2023 AND d.dec_level = 'FI' AND d.procedure_type = 'G' AND d.dec_pc = 'P'
    AND d.coo_iso NOT IN ('UNK','Various','-','STA','XXA','XXX','VAR','')
  GROUP BY d.coa_iso, d.coo_iso
  HAVING SUM(d.dec_recognized + d.dec_other + d.dec_rejected) >= 100
),
wts AS ( SELECT orig, SUM(substantive) AS w FROM cell GROUP BY orig )   -- global origin mix = standard population
SELECT
  cell.dest,
  ROUND(SUM(cell.protected)    * 100.0 / NULLIF(SUM(cell.substantive), 0), 1) AS trr_raw_pct,
  ROUND(SUM((cell.protected*1.0/NULLIF(cell.substantive,0)) * wts.w)
        / NULLIF(SUM(wts.w), 0) * 100.0, 1)                                    AS trr_std_pct
FROM cell JOIN wts ON cell.orig = wts.orig
GROUP BY cell.dest
ORDER BY trr_raw_pct DESC;
```

Chart: **slope / dumbbell** (raw rank → standardized rank); lines that cross = the paradox.
(The full direct/indirect standardization can also be done in Python from the `cell` CTE.)

### S4 — Regression-input aggregate (feeds the logistic forest plot)

The odds-ratio forest plot is **Python/statsmodels** (binomial GLM:
`protected ~ C(destination) + C(year)`), not SQL — but the model needs a tidy
per-(destination, year) success/trial aggregate. This pattern returns exactly that:

```sql
WITH europe(iso) AS (VALUES /* …same 32 rows… */
  ('AUT'),('BEL'),('BGR'),('HRV'),('CYP'),('CZE'),('DNK'),('EST'),('FIN'),('FRA'),
  ('DEU'),('GRC'),('HUN'),('IRL'),('ITA'),('LVA'),('LTU'),('LUX'),('MLT'),('NLD'),
  ('POL'),('PRT'),('ROU'),('SVK'),('SVN'),('ESP'),('SWE'),('ISL'),('NOR'),('CHE'),
  ('GBR'),('LIE'))
SELECT
  d.coa_iso AS destination, d.year,
  SUM(d.dec_recognized + d.dec_other)                                  AS protected,   -- successes
  SUM(d.dec_recognized + d.dec_other + d.dec_rejected)                 AS substantive  -- trials
FROM workspace.hackathon.asylum_decisions d
JOIN europe e ON d.coa_iso = e.iso
WHERE d.coo_iso = 'AFG'
  AND d.year BETWEEN 2018 AND 2023
  AND d.dec_level = 'FI' AND d.procedure_type = 'G' AND d.dec_pc = 'P'
GROUP BY d.coa_iso, d.year
HAVING SUM(d.dec_recognized + d.dec_other + d.dec_rejected) >= 50
ORDER BY destination, year;
```

In Python: `glm(formula='protected + (substantive-protected) ~ C(destination, Treatment("DEU")) + C(year)',
family=Binomial())` → exponentiate coefficients for odds ratios, take `conf_int()` for 95% CIs.
Story: Sweden OR ≈ 0.06 (~17× lower odds than Germany, year-adjusted).

> **Reference-Germany sanity check:** S1 with `coo_iso='AFG'`, 2023 should put Germany
> near the top (~96%) and Sweden near the bottom (~40%). If not, re-check `dec_level='FI'`.

---

## Anti-patterns — do NOT do these

❌ **Filter `dec_level = 'F'`** — there is no `'F'` value; first instance is **`'FI'`**.
   This silently returns ZERO rows and is the #1 way to break a lottery story.
❌ **Report a cross-country recognition rate over `dec_total`** — use **TRR** (closures
   excluded) for fairness comparisons; closures are procedural and vary wildly by state.
❌ **Use `region IN ('Europe')` for the lottery cohort** — it's a loose approximation
   that changes n. Use the 32-ISO `europe` allow-list CTE.
❌ **Aggregate `solutions` string columns without `try_cast`** — fails
   loudly or silently returns 0.
❌ **Include `dec_closed` in a "rejection rate"** (R13) — closures are
   administrative, not denial-on-merits.
❌ **Surface recognition rate without `dec_total`** — a 100% rate from 1
   decision is meaningless.
❌ **Combine `applied` and `dec_total` for the same year without R11
   caveat** — decisions reached in year Y came mostly from applications
   filed in Y-1, Y-2, Y-3.
❌ **Group by `coo`/`coa`** — UNHCR-internal codes; mis-attributes
   countries.
❌ **Show "Unknown" in a top-N leaderboard** — sentinel rows.

---

## Reference queries for validation

After deploying, these queries should produce sensible answers (rough
ballparks; not exact since the dataset can update):

| Query | Expected magnitude (2023) |
|---|---|
| EU asylum applications, total | ~1.1M |
| Global resettlement total | ~70K-100K |
| Global naturalisation total | depends on year; ~50K-150K typical |
| Recognition rate for Syrian applicants in Germany | typically >80% in recent years |
| Recognition rate for Afghan applicants in EU | typically 40-60% |

Use these to sanity-check after deploy; tune the agent's first-week
output against the EDA's published values.

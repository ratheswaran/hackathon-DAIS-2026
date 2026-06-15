---
name: data-story-composition
description: >
  How to compose D3 data-story infographics with the `compose_infographic`
  scene engine (single chart OR multi-panel report story) and the
  `compose_story` freehand escape hatch (bespoke scrollytelling). Covers the
  18 chart archetypes, when to pick each (grounded in the Cleveland–McGill
  perceptual hierarchy), the data-injection model, the editorial "reframe"
  spine, sober UNHCR voice, and the methodology/sourcing apparatus. Use
  whenever the agent is about to emit a chart, KPI, or visual story.
---

# Data-Story Composition Skill

> You build **single-file D3 data stories** from stored DataFrames. There are
> two tools. **`compose_infographic`** is the default — a *scene engine*: you
> pass an ordered list of typed scene dicts and it renders one chart (1 scene)
> or a multi-panel **report story** (many scenes: kicker → hero stat cards →
> titled chart panels → methodology). **`compose_story`** is the freehand
> escape hatch — only for a *bespoke scroll-driven essay* the archetypes can't
> express. Prefer `compose_infographic`.

This is the Resonance Analytics visual layer for the UNHCR / DAIS-for-Good
agent. The subject is forced displacement. The voice is sober; the craft is
exacting; every number is grounded in a query, never hand-typed.

---

## 1. The scene engine — `compose_infographic`

```python
compose_infographic(
  title="Forced displacement is the most concentrated crisis on earth",
  kicker="UNHCR · Resonance Analytics",        # eyebrow above the title
  lede="A handful of country-to-country flows account for almost all of it.",
  stats=[                                       # optional hero stat cards (the reframe up top)
    {"value": "0.98", "label": "Gini across all origin→asylum flows (1.0 = total concentration)"},
    {"value": "76%",  "label": "of refugees sit in the top 1% of country-pairs"},
  ],
  scenes=[                                       # ORDERED list — 1 = single chart, many = report story
    {"type": "lorenz_gini", "eyebrow": "CONCENTRATION · 01",
     "title": "How unequal? The Lorenz curve.",
     "lede": "The diagonal is perfect equality; the bowed line is reality.",
     "variable_name": "refugee_pairs_2024", "mapping": {"value_col": "refugees"},
     "caption": "End-2024 refugee stocks across ~4,700 origin×asylum pairs."},
    {"type": "ranked_bar", "eyebrow": "CONCENTRATION · 02",
     "title": "The ten origins behind most of the world's refugees.",
     "variable_name": "top_origins", "mapping": {"label_col": "origin", "value_col": "refugees"},
     "highlight": "Syria", "value_label": "refugees", "top_n": 10},
  ],
  methodology="End-of-year stocks, joined on ISO3; sentinel codes excluded. "
              "Gini computed across all pairs with ≥1 refugee.",
  source_note="UNHCR Refugee Data Finder, CC BY 4.0, pulled 2026-05-06.",
)
```

Returns `{"status":"ok","infographic_id":..,"url":"/api/infographics/<id>","scene_count":..}`.
**Surface ONLY the title in prose** — the frontend auto-opens the side panel from
`infographic_id`. Never paste the `url` or a `databricksapps.com/Volumes/...` link.

### How a scene gets its data — two ways

1. **`variable_name` + `mapping`** → the tool shapes the slice from a stored
   DataFrame. Supported for the SQL-friendly archetypes: `ranked_bar`,
   `line_multi`, `stacked_area`, `stacked_area_share`, `lorenz_gini`, `stat`.
2. **inline `data`** → you pass the precomputed slice. **Required** for the
   statistical archetypes that SQL can't produce — `forest_ci` (logistic
   odds-ratios + 95% CIs), `bubble_scatter` (OLS fit), `heatmap_matrix`,
   `choropleth`, `dumbbell`, `slope`, `pyramid`, `bar_race`, `iceberg`,
   `projection`, `sankey_corridors`, `kpi_grid`. Compute the dict in
   `run_python_code` over the stored DataFrame(s), then pass it as the scene's
   `data`. **Each archetype has a recipe** at `recipes/<type>.md` with the exact
   data shape, a sample, and a copy-paste compute snippet. Read the recipe before
   composing that scene.

> This mirrors the validated build pipeline (notebooks → findings.json →
> inject at `"__DATA__"`): no figure is hand-typed; everything is computed.

---

## 2. The 18 archetypes — pick by the QUESTION (Cleveland–McGill ranked)

Decoding accuracy falls in this order: **position on a common scale > length >
angle/area > colour/shading** (Cleveland & McGill 1984). Prefer position/length
encodings; reserve colour for categories or as a *secondary* channel where the
number is also printed (heatmap). Never use 3-D, never a pie/donut (angle+area
are low-rank — use `ranked_bar` or `kpi_grid` instead).

| Question the user is really asking | Archetype | Encoding |
|---|---|---|
| Who's biggest? rank / leaderboard | `ranked_bar` | length, common baseline |
| How has X changed over time? | `line_multi` | position |
| What's the absolute composition over time? | `stacked_area` | position/length |
| How has the *share* mix shifted? | `stacked_area_share` (100%) | position |
| How concentrated / unequal is it? | `lorenz_gini` | position + area |
| One headline number with weight | `stat` (or `count_up`) | text |
| A few headline numbers + deltas | `kpi_grid` | text + length(delta) |
| Is the treatment a lottery? (effect + uncertainty) | `forest_ci` | position on log scale + CI length |
| The lottery as texture (origin × destination) | `heatmap_matrix` | **number printed**, colour secondary |
| Does wealth predict burden? (correlation, honest null) | `bubble_scatter` | position (log–log) + area |
| Where, geographically? | `choropleth` | shading (Europe-framed) |
| Two-state comparison / gap per row | `dumbbell` | position + length(gap) |
| Rank reversal / Simpson's paradox | `slope` | position + crossing lines |
| Age–sex structure | `pyramid` | length, diverging from centre |
| Who led over time (changing ranks) | `bar_race` | length + motion |
| The reframe: the number behind the number | `iceberg` | length, above/below a waterline |
| Where is this heading? | `projection` | position + uncertainty band |
| The biggest flows origin→host | `sankey_corridors` | flow width |

**When two archetypes fit, prefer the higher-rank encoding** (e.g. `ranked_bar`
over a donut for composition; `dumbbell` over two separate bars for a 2-state gap).

---

## 3. The report story — structure a multi-scene deliverable

A *story* (≥2 scenes) is more than a chart dump. Sequence it:

1. **Kicker + serif title + lede** — the headline finding, human framing first.
2. **Hero stat cards (`stats=`)** — 2–3 numbers, leading with **the reframe**
   (the second number standing behind the first).
3. **Scene panels in narrative order** — each a titled chart that advances the
   argument; give each an `eyebrow` (`"SECTION · 0N"`), a one-line `lede`, and a
   `caption` that voices the finding.
4. **Methodology** — period, definitions, controls, limitations, source.

### The "reframe" editorial spine

Every strong UNHCR story shows **the second number behind the first**:

- headline refugee count → **iceberg**: most are IDPs who never crossed a border
- "generous nations" → **slope/dumbbell**: Simpson's paradox once you adjust for caseload
- absolute hosting leaderboard → **per-capita**: Lebanon/Chad carry the real weight
- "asylum is asylum" → **forest_ci / heatmap_matrix**: a 17× lottery by destination

Lead with the reframe in the lede and the hero stat. State it plainly.

---

## 4. Voice (UNHCR data = real displaced people)

- **No emoji. No clickbait. No triumphalism** — a high ranking is a tragedy, not a podium.
- **Titles**: plain noun phrase, **time scope when the data has one**
  ("Top hosts of Sudanese refugees, end-2024"). Past/scope-bound tense, not present
  ("Sudan exceeded Syria on total displaced in 2024", not "Sudan IS the biggest crisis").
- **Lede**: 1–2 sentences, human framing first ("1.11 million people from Sudan
  sought protection in Chad" — not "Chad ranks #1"). Don't repeat the title.
- **Caption**: name the finding + the scope/denominator + any methodology caveat
  (R2 Venezuela OOC reclassification; R3 refugees vs asylum-seekers; R11 decisions
  lag applications 1–3 yrs; R13 closures ≠ rejections; TRR ≠ recognition-over-total).
- **Numbers**: `14.34 million` for ≥1M; `1,109,357` (commas) for 100K–1M; bare for
  <100K; `94.06%` not `0.9406`; signed deltas `+12.4%` / `−3.1%`. (The charts'
  axis/value labels auto-format K/M/B — you only format prose + stat-card values.)

---

## 5. Highlight-by-colour (the engine enforces it; you direct it)

Most series render **neutral grey**; only the entity the sentence names gets an
accent. Set `scene.highlight` to that entity's label (string) or labels (array).
The accent is cobalt `#254BB2` (amber on dark backgrounds). This is why the eye
lands where the prose points. Don't rainbow-colour everything.

Palette + type come from `tokens.css` (oat/ivory canvas, cobalt primary, amber/
cyan/magenta accents, Source Serif 4 display / Manrope / JetBrains Mono). You do
not pass colours — the engine applies them. See `../tokens.css` and `../SKILL.md`.

---

## 6. Motion & reliability — handled for you

The **scene engine** (`compose_infographic`) draws **final geometry first** and
fades in with a CSS animation (`animation-fill-mode: both`) — reliable under
screenshots and backgrounded tabs, and it honours `prefers-reduced-motion`. You
don't manage animation for infographics; opacity-only fade is the whole story there.

**`compose_story` is the opposite** — a flagship scrollytelling is *interactive
and scroll-driven*: the sticky chart **must change as the reader scrolls** (the
highlight walks, a series gets emphasised, data builds up, an annotation appears).
A static sticky chart that only fades in on load is a **bug**, not a safe default.
The scaffold already implements this; §7 has the rule. Reliability is still
honoured — step 0 paints the complete chart and every transition is wrapped in a
`prefers-reduced-motion` guard, so PNG/PDF exports come out static.

---

## 7. `compose_story` — the freehand flagship escape hatch

Use ONLY when the user wants a **bespoke scroll-driven essay** (e.g. a 3-chapter
sticky-scroll narrative where the chart in a pinned panel *swaps* as the reader
scrolls past prose steps) that the scene archetypes can't express. Otherwise use
`compose_infographic`.

```python
compose_story(
  title="The asylum lottery",
  template_html="<!DOCTYPE html>… const DATA = \"__DATA__\"; …",  # copy recipes/_flagship_scaffold.html
  data={...},   # EVERY figure, computed via run_python_code over stored DataFrames
)
```

It does **not** execute your code — it injects your `data` dict at the
`"__DATA__"` token (and the brand palette at an optional `"__PALETTE__"` token),
then publishes. So: (1) start from `recipes/_flagship_scaffold.html` (RA-branded,
scrollytelling skeleton), (2) compute the data dict in `run_python_code`,
(3) pass `template_html` + `data`. No number may be hand-typed in the template.

### 7a. THE MOTION IS THE SCROLL — non-negotiable

The sticky chart is a **state machine**, not a one-shot drawing. Each chapter's
renderer is `render(svg, ch, ci, si)`: it draws the chart in the state for step
`si`, is called once on load (`si=0`) and **again on every step change**, and
interpolates between states with a `d3` transition. That swap is the animation.

The scaffold already wires this end-to-end — keep it:

- `renderBars` / `renderLine` build geometry once (keyed `.data()` joins) then
  **`T(sel)`-transition** on later calls. `T()` is a real transition live and a
  no-op under `prefers-reduced-motion`.
- An `IntersectionObserver` marks the active `.step` and **re-invokes that
  chapter's renderer** with the new `si` — that line is the swap; never delete it.
- Per-step choreography lives in `data`: each step may carry
  `view: { highlight: "Sweden" | ["Germany","Sweden"], reveal: 8, annotate: {at,text} }`.
  Omit `view` and the engine still moves (the highlight walks the rows/series).
- Need a chart type beyond line/bars (rank, odds/CI, slope, heatmap)? **Add a
  renderer the same way** — `(svg, ch, ci, si)`, keyed joins, `T()` for the
  per-step change — and register it in `RENDER`. Do **not** fall back to a
  draw-once static chart.

Reliability holds: **step 0 must render the complete chart** (an unscrolled
screenshot is valid), and every per-step change goes through `T()` so reduced
motion / export paths stay static. This is the one place geometry *may* move on
scroll (bar grow-in, line clip-reveal) — because it's interactive, guarded, and
re-paints to a valid final state. Verify before you ship: scrolling a chapter
must visibly change its chart, not just dim the prose.

---

## 8. Anti-patterns

❌ Pie / donut / 3-D anything (low-rank encodings — use `ranked_bar`/`kpi_grid`).
❌ A chart for a single number — use `stat`, or just say it in one sentence.
❌ Rainbow / saturated palettes (subject is grave; cobalt+neutral, accent sparingly).
❌ Hand-typed figures in a story — compute everything; pass via `data` / `mapping`.
❌ Top-N leaderboard with sentinel rows — filter `coo_iso NOT IN ('UNK','Various','-',…)`.
❌ Pasting the infographic URL or a fabricated Volumes link in chat (reference by title).
❌ Recognition-rate-over-`dec_total` for a fairness comparison — use **TRR** (see the
   asylum-flow domain skill, R14). Per-capita burden without the World Bank ref table (R16).
❌ `compose_story` for a standard chart — that's `compose_infographic`'s job.

---

## 9. Cross-references

- Tool source: `tools/compose_infographic.py` (scene engine), `tools/compose_story.py` (freehand).
- Per-archetype data shapes + compute snippets: `recipes/<type>.md`; flagship
  scaffold: `recipes/_flagship_scaffold.html`.
- Palette/type single source: `../tokens.css`. Chart-choice theory:
  `../data-visualisation-chart-guidance/` (Cleveland–McGill hierarchy, proportional
  ink, colour encoding, no-3D).
- Story metric SQL (TRR, Gini, per-capita, matrix, corridors): the two domain
  skills' `sql_patterns.md` **S-series**; cohort/suppression rules R14–R16.
- Source footer always: "UNHCR Refugee Data Finder (api.unhcr.org/population/v1/),
  CC BY 4.0" (+ "Host population & GDP: World Bank, CC BY 4.0" when burden stories use R16).

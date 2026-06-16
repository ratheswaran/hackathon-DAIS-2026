---
name: hackathon-design-system
description: >
  Editorial-style design system for the hackathon agent's visual output. Sober
  palette, chart-selection guidance, voice rules. Points at the four installed
  Claude design skills (data-journalism, d3js-visualization,
  pudding-visual-storytelling, html-effectiveness) plus the langchain-deepagents
  framework reference as the underlying toolkit. Use when picking a chart shape,
  applying color, or laying out a multi-panel visual.
---

# Hackathon Design System

> **DRY-RUN ARTIFACT.** Editorial design system for the hackathon agent's
> visual output. The actual hackathon submission inherits directly from the
> four Claude design skills below — there is no separate brand to preserve.
> This file mainly enforces *voice* and pins the editorial palette so the
> orchestrator's chart output looks editorial, not corporate.

## Voice + tone

The subject is real people's access to care. Agent voice is **sober**:

- No emoji.
- No clickbait phrasings ("you won't believe…", "shocking", "crisis explodes 🚨").
- No triumphalist framing of "top" rankings — they describe gaps in care.
- Plain prose; the numbers carry the weight.
- Lead with human framing in plain text BEFORE the chart, not after:
  "245 of the surveyed districts have no facility in this coverage sample,
   leaving residents to travel for routine care."

## Underlying Claude skills

The hackathon agent **does not invent its own design language**. It leans on
four installed Claude skills (locations: `~/.claude/skills/`):

| Skill | Role | Where invoked |
|---|---|---|
| `data-journalism` | Story arc (hook → evidence → context → human element → implications → methodology), AI-disclosure block, source-citation footer | Every analytical answer |
| `html-effectiveness` | Decide format (markdown vs single-file HTML), pick from the 9 archetypes, enforce editorial palette | When emitting a rich deliverable |
| `pudding-visual-storytelling` | Narrative spine: pinned-narrative (default), progressive-reveal, parallax, step-sequence; IntersectionObserver step triggers; reduced-motion fallbacks | When emitting a multi-step scrolly |
| `d3js-visualization` | The actual chart implementation in D3.js (v7+). Replaces Plotly for any non-trivial chart. | Chart rendering |

**A 5th candidate** (per user note 2026-05-12): `langchain-deepagents` — the
framework reference for the orchestrator itself. Pull when adding tools,
middleware, or subagents.

## Direction: the D3 scene engine (built)

The hackathon agent ships rich output as a **standalone single-file `.html`
artifact** opened in a side panel — never inline Plotly. The chat stays
scannable; the visual lives in a dedicated viewport. This is now a **built
scene engine**, not a plan:

- **`compose_infographic`** — 18 native D3 archetypes; one scene = a chart,
  many scenes = a multi-panel report story. The default.
- **`compose_story`** — freehand bespoke scrollytelling escape hatch.

**Read [infographics/SKILL.md](infographics/SKILL.md) — it is the PRIMARY
composition skill** (archetype catalogue, when-to-pick, data-injection model,
report-story structure, voice, recipes). This file pins the brand + voice; that
file tells you how to compose.

## Brand palette — RECONCILED RA-EDITORIAL (single source: `tokens.css`)

The deck/PPTX brand is RA cobalt "Signal"; the data-stories adopt that cobalt as
the **primary data accent** on a warm-neutral **editorial** canvas. One token set,
defined once in **[`tokens.css`](tokens.css)** (CSS vars + mirrored JS + Python).
You do **not** pass colours to the engine — it applies them. Reference:

| Token | Hex | Role |
|---|---|---|
| `--paper` / `--oat` | `#FAF6EE` / `#F5EFE3` | page / card canvas (warm ivory) |
| `--ink` / `--slate` / `--mute` | `#1F1B16` / `#3A3A40` / `#9CA0A3` | text / secondary / ticks |
| `--grey` | `#C7C2B6` | neutral series (everything NOT highlighted) |
| `--signal` | `#254BB2` | **cobalt — primary series / the highlighted entity** |
| `--amber` / `--cyan` / `--magenta` | `#DF9B44` / `#2695AC` / `#913F82` | secondary / tertiary / 4th |
| `--alarm` | `#A6402E` | negative deltas, suppression (sparing) |

Fonts: **Source Serif 4** (display: hero, titles, stat values, quotes) ·
**Manrope** (body / UI / axes) · **JetBrains Mono** (numbers, captions).
NO bright reds, NO rainbow scales — the subject is people's access to care. ⚠ Earlier clay/olive
editorial and pure-cobalt-on-white palettes are SUPERSEDED — use `tokens.css`.

## Chart selection — question class → scene archetype

Map the user-question class to a `compose_infographic` archetype (full catalogue
+ the Cleveland–McGill rationale in [infographics/SKILL.md](infographics/SKILL.md)).
Prefer position/length encodings; **never pie/donut/3-D** (low-rank angle/area).

| Question class | Archetype |
|---|---|
| Single KPI ("how many facilities in district X?") | plain text, or `stat` if it needs weight |
| A few headline numbers + deltas | `kpi_grid` |
| Top-N leaderboard | `ranked_bar` (highlight the named entity) |
| Time series / comparison | `line_multi` |
| Composition over time (absolute / share) | `stacked_area` / `stacked_area_share` |
| Concentration / inequality | `lorenz_gini` |
| District × indicator intensity | `heatmap_matrix` (% printed in cell) |
| Access-gap odds + uncertainty | `forest_ci` (odds ratios + CIs) |
| Correlation / honest null | `bubble_scatter` (log–log + OLS) |
| Geographic pattern | `choropleth` (India-district-framed) |
| Two-state gap / rank reversal | `dumbbell` / `slope` |
| Age–sex structure | `pyramid` |
| Changing ranks over time | `bar_race` |
| The reframe (number behind the number) | `iceberg` |
| Where it's heading | `projection` |
| Biggest flows origin→host | `sankey_corridors` |
| Cell-suppressed demographic table | markdown table with `<5` annotations (not a chart) |

## Number formatting

- No scientific notation in user-facing numbers.
- Counts: comma-thousands. Use K/M suffix at ≥ 100,000 for axis labels only:
  - 14,340,000 in body text
  - 14.3M on a chart axis
- Percentages: 1 or 2 decimal places, `%` suffix. "94.06%" not "0.9406".
- YoY change: signed, `+12.4%` or `−3.1%` (use minus sign, not hyphen, in
  user-facing text — accessibility).

## Methodology + AI-disclosure footer (data-journalism skill)

Every analytical answer ends with a methodology footer. The compose tools
inject the canonical source line automatically — do not hand-write a
contradictory one. The shape is:

```
─────
Source: Virtue Foundation dataset (facilities, india_post_pincode_directory,
nfhs_5_district_health_indicators).
Methodology: [facility coverage from a ~10k sample, NOT a census | NFHS-5
district health indicators | India Post PIN → district crosswalk]. Facility
service claims are self-reported. No per-capita rates (no population in source).
AI-disclosure: Answer composed by an LLM agent. Numbers retrieved by SQL under
the user's identity; figures verified against the source tables where available.
─────
```

Compact form (chat replies):

> *Source: Virtue Foundation dataset. Coverage sample, not a census. AI-composed.*

## Reference files

- **[infographics/SKILL.md](infographics/SKILL.md)** —
  **PRIMARY composition skill.** Decision tree + template reference for the
  `compose_infographic` tool. Roll-in of data-journalism + d3js-visualization
  + pudding-visual-storytelling + html-effectiveness. Read this when the
  agent is about to call `compose_infographic`.
- **[data-visualisation-chart-guidance/SKILL.md](data-visualisation-chart-guidance/SKILL.md)** —
  General chart-selection matrix + design rules (legacy from v3; useful for
  cross-referencing chart-type choice but supplanted by the infographics
  decision tree for the hackathon agent).
- The four Claude design skills (above) live OUTSIDE this folder, in
  `~/.claude/skills/`, and are autoloaded by the runtime.

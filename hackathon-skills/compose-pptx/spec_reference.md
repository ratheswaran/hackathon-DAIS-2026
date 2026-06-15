# Deck Spec Reference — Resonance Analytics

The `compose_deck` tool consumes a list of slide dicts. Each slide has a
`type` field that selects the layout, plus content fields. The tool
renders the spec to PPTX (python-pptx, native charts) and HTML (preview)
from the same source of truth.

Slide canvas is **1920 × 1080** (16:9 widescreen, matches PowerPoint
`LAYOUT_WIDE`). You don't position by pixels.

## Top-level call

```python
compose_deck(
    title="The Asylum Lottery — DAIS for Good 2026",
    deck_spec=[
        {"type": "cover",    "title": "The Asylum Lottery", "lede": "...", "eyebrow": "DAIS FOR GOOD · 2026"},
        {"type": "data_note", ...},
        {"type": "stat_callout", ...},
        {"type": "kpi_grid",     ...},
        {"type": "chart",        ...},
        {"type": "two_column",   ...},
        {"type": "closing",      "title": "One Convention, one standard", "lede": "..."},
    ],
)
```

## Common fields on EVERY slide

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `type` | str | required | One of the slide types below |
| `eyebrow` | str | "" | Short label above the title (uppercase + dash). E.g. `"FINDINGS · 02"`. Renders cobalt on light backgrounds, **amber** on dark. |
| `bg` | str | `"paper"` | `"paper"` (white) · `"cream"` (warm off-white) · `"signal"` (cobalt, white text) · `"ink"` (near-black poster, white text). Aliases `"red"`→signal, `"charcoal"`/`"dark"`→ink are accepted. |
| `footer_note` | str | "" | Bottom-left small text; the deck page number is always on the right. |
| `motif` | bool | `true` | On `cover` / `closing` with a dark (`ink`) background, draws the cobalt **orb**. Set `false` to suppress. |

> **There is no `logo` field.** The Resonance Analytics brand-mark +
> wordmark are drawn automatically on `cover`, `section_divider`, and
> `closing` slides; a small brand-mark sits by the page number on content
> slides. Don't add a `logo` key.

---

## Slide Types

### `cover` — first slide

```json
{
  "type": "cover",
  "bg": "ink",
  "eyebrow": "DAIS FOR GOOD · 2026",
  "title": "The Asylum Lottery",
  "lede": "Why identical claims meet opposite fates across Europe."
}
```

| Field | Notes |
|-------|------|
| `title` | Hero text in Source Serif 4 display (~72pt). ≤8 words. |
| `lede` | One-line subtitle. ≤24 words. |

Default `bg` is `"ink"` — the dark cobalt-orb poster (the RA signature).
Use `bg:"signal"` for a solid-cobalt cover, or `bg:"paper"` for a light
cover, only with a reason.

### `section_divider`

```json
{
  "type": "section_divider",
  "bg": "signal",
  "eyebrow": "SECTION · 02",
  "title": "Recommendations",
  "lede": "Three levers."
}
```

Use ONCE per major act. Don't use as a "spacer" between content. `signal`
(cobalt) or `ink` (dark) both work; `paper` for a light divider.

### `stat_callout` — single hero number

```json
{
  "type": "stat_callout",
  "eyebrow": "HEADLINE",
  "title": "Afghan recognition gap",
  "value": "17x",
  "unit": "lower",
  "delta": "Sweden vs Germany",
  "delta_dir": "down",
  "caption": "Year-adjusted odds of protection under the same Convention."
}
```

| Field | Notes |
|-------|------|
| `value` | The number. Renders at ~130pt Source Serif in cobalt **Signal** (the one emphatic brand moment). Use K/M/B/x suffixes — don't dump 12 digits. |
| `unit` | Small label after the value (`"%"`, `"M"`, `"lower"`) |
| `delta` | Optional change figure (`"+12.4% YoY"`, `"Sweden vs Germany"`) |
| `delta_dir` | `"up"` (green) / `"down"` (red) / `"flat"` (slate) |
| `caption` | One-line interpretation. The number alone is not the insight. |

**One `stat_callout` per deck max.** Every other number lives in a
`kpi_grid` or `chart`.

### `kpi_grid` — 3-4 supporting metrics

```json
{
  "type": "kpi_grid",
  "eyebrow": "AT A GLANCE",
  "title": "Four signals",
  "kpis": [
    {"label": "ORIGINS",     "value": "104",  "unit": "ctry", "delta": "+6",   "delta_dir": "up"},
    {"label": "RECOGNITION", "value": "42",   "unit": "%",    "delta": "-3pp", "delta_dir": "down"},
    {"label": "BACKLOG",     "value": "1.2",  "unit": "M",    "delta": "+11%", "delta_dir": "up"},
    {"label": "HOSTS",       "value": "38",   "unit": "",     "delta": "flat", "delta_dir": "flat"}
  ],
  "caption": "EMEA, 2023."
}
```

Best with exactly 3 or 4 tiles. ≤6 max. Each tile is a rounded card with
a cobalt accent tick, uppercase label, and a Source Serif value.

### `bullets` — title + lede + bullet list

```json
{
  "type": "bullets",
  "eyebrow": "RECOMMENDATIONS",
  "title": "Three things to do this quarter",
  "lede": "Ranked by expected impact.",
  "bullets": [
    "Harmonise country-of-origin guidance across the bloc.",
    "Audit accelerated procedures in low-recognition corridors.",
    "Publish an open first-instance recognition dashboard."
  ]
}
```

Don't use as a default. **Always prefer a chart, KPI grid, or stat
callout where the data fits.** Bullets are the lowest-effort slide and
read that way.

### `two_column` — side-by-side comparison

```json
{
  "type": "two_column",
  "eyebrow": "FINDINGS · 02",
  "title": "What moves the odds",
  "left":  {"heading": "Helps", "bullets": ["Country-of-origin guidance", "Legal representation", "Appeal access"]},
  "right": {"heading": "Hurts", "bullets": ["Accelerated procedures", "Safe-country lists", "Detention"]}
}
```

Equal-width columns. ≤4 bullets per side.

### `chart` — NATIVE PowerPoint chart

```json
{
  "type": "chart",
  "eyebrow": "CHARTS · 01",
  "title": "Recognition rate by destination",
  "chart": "column",
  "categories": ["Germany", "Sweden", "France", "Italy", "Spain"],
  "series": [
    {"name": "Rate", "values": [96, 40, 62, 55, 71]}
  ],
  "value_label": "%",
  "caption": "Afghans, first instance, 2023. Germany recognises 96%, Sweden 40% — same Convention.",
  "show_values": true,
  "show_legend": false
}
```

| Field | Notes |
|-------|------|
| `chart` | `"column"` (vertical) / `"bar"` (horizontal) / `"line"` / `"pie"` |
| `categories` | x-axis labels (or pie slice labels) |
| `series` | List of `{"name", "values"}`. ONE series for `pie`; up to 6 for column/bar/line |
| `value_label` | Value-axis title (rendered in the PPTX for column/bar/line; ignored for pie and in the HTML preview). "" to omit. |
| `caption` | One-line interpretation. Always include. |
| `show_values` | True (default) shows data labels on column / bar / pie. (Line charts never show point labels — keep them clean.) |
| `show_legend` | False (default) for single-series. True if 2+ series |

**Chart palette ordering** (assigned in series order):

1. `254BB2` — cobalt **Signal** (lead)
2. `DF9B44` — amber
3. `2695AC` — cyan
4. `913F82` — magenta
5. `85B0FF` — light cobalt
6. `52657A` — slate (neutral / "rest")

**Sort rules:**

- **Column/bar**: sort categories by value descending unless they have a
  natural order (months, regions).
- **Pie**: largest segment at 12 o'clock, clockwise descending. Group
  anything under 5% into "Other".
- **Line**: chronological. Don't sort by value.

### `chart_commentary` — chart + sidebar bullets

```json
{
  "type": "chart_commentary",
  "bg": "ink",
  "eyebrow": "ANALYSIS · 02",
  "title": "Diverging trajectories",
  "chart": "line",
  "categories": ["2019", "2020", "2021", "2022", "2023"],
  "series": [
    {"name": "Germany", "values": [88, 90, 92, 95, 96]},
    {"name": "Sweden",  "values": [60, 55, 48, 44, 40]}
  ],
  "value_label": "%",
  "show_legend": true,
  "commentary": [
    {"label": "Germany held",  "text": "Steady above 90% throughout."},
    {"label": "Sweden fell",   "text": "Down 20pp over five years."},
    {"label": "Gap widened",   "text": "Divergence accelerated post-2021."}
  ]
}
```

Chart ~60% width, commentary ~40%. Each `commentary` item is a bold
cobalt (or amber, on dark) label + a short paragraph. 3-4 items max. On a
dark (`ink`) background the chart axes + legend auto-switch to white.

> The tool is forgiving about `commentary` shape — a list of
> `{label,text}` is canonical, but a `{"title":..,"bullets":[..]}` dict
> or a bare list of strings is coerced automatically.

### `table`

```json
{
  "type": "table",
  "eyebrow": "DATA · 01",
  "title": "Top hosts by first-instance claims",
  "headers": ["Country", "Claims", "Rate %"],
  "rows": [
    ["Germany", "244,132", "96"],
    ["France",  "137,510", "62"],
    ["Sweden",  "41,205",  "40"]
  ],
  "caption": "2023. Header row is cobalt; numeric columns right-aligned with tabular numerals."
}
```

≤6 rows × ≤5 cols. The tool right-aligns columns whose header contains a
unit or `%` (recognises `%`, `THB`, `USD`, `EUR`, `GBP`, `(M)`, `Δ`).

### `quote`

```json
{
  "type": "quote",
  "bg": "cream",
  "eyebrow": "VOICE · CASEWORKER",
  "quote": "Same flight, same war, two verdicts.",
  "attribution": "Asylum caseworker · Berlin",
  "caption": "Recurring theme across interviews."
}
```

Quote text is Source Serif 4 italic, ~40pt. A breather between dense
slides. `cream` (warm) or `paper` work well.

### `data_note` — required when substituting periods/scope

```json
{
  "type": "data_note",
  "eyebrow": "DATA NOTE",
  "title": "Scope",
  "requested": "2024 full-year",
  "available": "2014–2023",
  "reason": "UNHCR Refugee Data Finder lags one annual cycle."
}
```

ALWAYS the second slide (right after cover) when the user asked for data
the source doesn't cover. Don't bury it later.

### `timeline`

```json
{
  "type": "timeline",
  "eyebrow": "PLAN · NEXT 90 DAYS",
  "title": "Roll-out cadence",
  "steps": [
    {"label": "Q1", "heading": "Harmonise guidance", "body": "Agree a common country-of-origin baseline."},
    {"label": "Q2", "heading": "Audit fast-track",   "body": "Flag low-recognition corridors for review."},
    {"label": "Q3", "heading": "Publish",            "body": "Ship the open recognition dashboard."}
  ]
}
```

3-5 steps. Each is a cobalt rail label + bold heading + body sentence.

### `closing`

```json
{
  "type": "closing",
  "bg": "ink",
  "eyebrow": "NEXT STEPS",
  "title": "One Convention, one standard",
  "lede": "Owner: Policy · Review: end-Q1"
}
```

Mirrors the cover in inverse — defaults to the dark `ink` poster. Use to
state the ask, not to thank the audience.

---

## Brand-mark (automatic)

The Resonance Analytics brand-mark — a cobalt rounded square with a small
cross-hair — plus the "Resonance Analytics" wordmark are drawn
automatically on `cover`, `section_divider`, and `closing` slides. A
small brand-mark sits next to the page number on content slides. You
don't reference it in the spec and there is **no `logo` field**.

---

## Required: caption on every chart/KPI/stat slide

Every `stat_callout`, `chart`, `chart_commentary`, `kpi_grid`, and
`table` MUST have a `caption` (or, for `kpi_grid`, a meaningful `title` +
`eyebrow`). The number alone is not the insight. The caption names:
scope, period, and one interpretation.

Bad:  `"caption": "Recognition by country"`  (re-states the title)
Good: `"caption": "Germany recognises 96% of Afghan claims, Sweden 40% — a 56pp gap under the same Convention."`

---

## Sanity checklist before calling the tool

- [ ] Every slide has a `type` from the catalogue
- [ ] No `value`/`title`/`caption` is an empty string
- [ ] No "Lorem ipsum" / "TBD" / "Insert content here"
- [ ] Cobalt Signal used for emphasis; accents (amber/cyan/magenta) stay supporting
- [ ] Each chart's `series[*].values` length matches `categories` length
- [ ] Each `chart` has a `caption`
- [ ] Cover + ≥1 content + closing (closing recommended, not required)
- [ ] If scope/period was substituted, the SECOND slide is a `data_note`
- [ ] No `logo` field anywhere (the brand-mark is automatic)

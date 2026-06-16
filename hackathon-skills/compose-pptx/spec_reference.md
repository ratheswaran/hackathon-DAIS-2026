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
    title="The Care Lottery — DAIS for Good 2026",
    deck_spec=[
        {"type": "cover",    "title": "The Care Lottery", "lede": "...", "eyebrow": "DAIS FOR GOOD · 2026"},
        {"type": "data_note", ...},
        {"type": "stat_callout", ...},
        {"type": "kpi_grid",     ...},
        {"type": "chart",        ...},
        {"type": "two_column",   ...},
        {"type": "closing",      "title": "Close the access gap", "lede": "..."},
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
  "title": "The Care Lottery",
  "lede": "Why district health access varies up to 80x across India."
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
  "title": "Districts with zero facilities",
  "value": "245",
  "unit": "of 698",
  "delta": "NFHS-5 districts",
  "delta_dir": "down",
  "caption": "Sampled facility coverage shows no listed facility in 245 of 698 NFHS-5 districts."
}
```

| Field | Notes |
|-------|------|
| `value` | The number. Renders at ~130pt Source Serif in cobalt **Signal** (the one emphatic brand moment). Use K/M/B/x suffixes — don't dump 12 digits. |
| `unit` | Small label after the value (`"%"`, `"M"`, `"lower"`) |
| `delta` | Optional change figure (`"+12.4% YoY"`, `"Bihar vs Kerala"`) |
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
    {"label": "DISTRICTS",   "value": "698",  "unit": "",     "delta": "+6",   "delta_dir": "up"},
    {"label": "ZERO-FAC",    "value": "35",   "unit": "%",    "delta": "-3pp", "delta_dir": "down"},
    {"label": "FACILITIES",  "value": "10",   "unit": "K",    "delta": "+11%", "delta_dir": "up"},
    {"label": "WORST HBI",   "value": "78",   "unit": "",     "delta": "flat", "delta_dir": "flat"}
  ],
  "caption": "NFHS-5 districts, sampled facility coverage."
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
    "Prioritise the high-burden, zero-facility districts first.",
    "Verify self-reported facility capabilities before referral.",
    "Publish an open district access-gap dashboard."
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
  "title": "What moves access",
  "left":  {"heading": "Helps", "bullets": ["Nearby facility", "Verified specialties", "Public transport links"]},
  "right": {"heading": "Hurts", "bullets": ["Rural distance", "Unverified claims", "Single-facility districts"]}
}
```

Equal-width columns. ≤4 bullets per side.

### `chart` — NATIVE PowerPoint chart

```json
{
  "type": "chart",
  "eyebrow": "CHARTS · 01",
  "title": "Health Burden Index by state",
  "chart": "column",
  "categories": ["Bihar", "UP", "MP", "Rajasthan", "Kerala"],
  "series": [
    {"name": "HBI", "values": [78, 71, 66, 59, 17]}
  ],
  "value_label": "HBI",
  "caption": "NFHS-5 districts. Bihar HBI 78 vs Kerala 17 — a wide access gap across states.",
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
  "categories": ["2015", "2017", "2019", "2021", "2023"],
  "series": [
    {"name": "Kerala", "values": [22, 20, 19, 18, 17]},
    {"name": "Bihar",  "values": [70, 72, 74, 76, 78]}
  ],
  "value_label": "HBI",
  "show_legend": true,
  "commentary": [
    {"label": "Kerala low",   "text": "Held below 25 throughout."},
    {"label": "Bihar rose",   "text": "Up 8 points over the window."},
    {"label": "Gap widened",  "text": "Divergence accelerated post-2019."}
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
  "title": "Top states by facility count",
  "headers": ["State", "Facilities", "Zero-fac %"],
  "rows": [
    ["Maharashtra", "1,204", "18"],
    ["Tamil Nadu",  "  876", "22"],
    ["Bihar",       "  205", "61"]
  ],
  "caption": "Sampled coverage. Header row is cobalt; numeric columns right-aligned with tabular numerals."
}
```

≤6 rows × ≤5 cols. The tool right-aligns columns whose header contains a
unit or `%` (recognises `%`, `USD`, `EUR`, `GBP`, `(M)`, `Δ`).

### `quote`

```json
{
  "type": "quote",
  "bg": "cream",
  "eyebrow": "VOICE · FIELD HEALTH WORKER",
  "quote": "Same need, two districts, very different care.",
  "attribution": "Community health worker · Bihar",
  "caption": "Recurring theme across field visits."
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
  "requested": "Facility census",
  "available": "~10k sampled facilities",
  "reason": "Facilities is a sample, not a census — read as coverage, not total supply."
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
    {"label": "Q1", "heading": "Rank deserts",  "body": "Score high-burden, zero-facility districts."},
    {"label": "Q2", "heading": "Verify claims", "body": "Flag unverified specialty claims for review."},
    {"label": "Q3", "heading": "Publish",       "body": "Ship the open district access-gap dashboard."}
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
  "title": "Close the access gap",
  "lede": "Owner: Planning · Review: end-Q1"
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

Bad:  `"caption": "Health burden by state"`  (re-states the title)
Good: `"caption": "Bihar HBI 78 vs Kerala 17 — a wide access gap across NFHS-5 districts."`

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

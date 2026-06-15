# Design — Resonance Analytics Brand, Type, Layout Discipline

Read this only if the user asks for a specific visual brief ("match the
brand colours", "go monochrome", "make it more editorial"). For most
decks the defaults baked into `compose_deck` are correct.

The canonical source is the **Resonance Analytics Design System Deck**
(`design_system_deck_example.html` + `tokens.css` in this folder) — an
original "Boardroom Editorial" system. Read that file for worked examples
of every layout and chart.

## Defaults (built into the tool)

| | Value | Why |
|---|---|---|
| Primary | **Signal** cobalt-indigo `#254BB2` | Brand spine — dominant on covers, dividers, table headers, lead chart series |
| Neutrals | **ink** cool-slate, `#050A0F` text → `#F9FAFC` paper | Body + structure |
| Surface | White `#FFFFFF` and warm cream `#FBF0E4` | Information-rich backgrounds |
| Display type | Source Serif 4 (serif) | Covers, hero numbers, section openers, pull-quotes |
| Body/UI type | Manrope (sans) | Titles, body, labels, UI |
| Mono | JetBrains Mono | Page numbers, small data labels |
| Slide size | 1920 × 1080 px | 16:9, matches PPTX widescreen exactly |

## Palette (canonical — from tokens.css)

Tokens are authored in `oklch`; the hex values below are the sRGB
renderings used by the PPTX renderer.

### Signal — cobalt-indigo brand scale

```
--signal-50   #F0F5FF
--signal-100  #DAE9FF
--signal-200  #B5D2FF
--signal-300  #85B0FF   light cobalt (chart accent 5)
--signal-400  #5080EB
--signal-500  #345FCF   orb highlight
--signal-600  #254BB2   PRIMARY — accent, emphasis, table header
--signal-700  #17368D   solid cobalt background (bg:"signal")
--signal-800  #0A2163
--signal-900  #051139
```

### Ink — cool-slate neutrals

```
--ink-50   #F9FAFC   paper
--ink-100  #EFF2F5   surface-2 / zebra row
--ink-200  #E1E5E9   border
--ink-300  #C6CBD0   muted on dark
--ink-400  #9A9FA5
--ink-500  #6D7277   soft text / captions
--ink-600  #494E52   muted text
--ink-700  #2F3338
--ink-800  #161B20
--ink-900  #050A0F   body text
--ink-950  #010204   dark poster background (bg:"ink")
```

### Accents (chart + infographic palette)

Harmonized with the cobalt primary. Use sparingly; never let an accent
dominate a composition — pull it back to cobalt or ink.

```
--gold   #DF9B44   amber   (chart accent 1 · eyebrow on dark backgrounds)
--teal   #2695AC   cyan    (chart accent 2)
--plum   #913F82   magenta (chart accent 3)
--slate  #52657A   neutral (chart "rest")
--sand   #BDD5E6   tints
```

### Status

```
--success #14874E   green  (delta up)
--warning #D79628   amber
--danger  #BA2B2E   red    (delta down)
```

## Type Scale

```
display-xl   128 px / Source Serif 400   cover hero only
display-l     88 px / Source Serif 400   big stat, large cover
display-m     64 px / Source Serif 400   section title
h1            48 px / Manrope 600        secondary title
h2            36 px / Manrope 600        slide title, subsection
h3            28 px / Manrope 600        card title
body-l        22 px / Manrope 400        lede paragraphs
body          18 px / Manrope 400        default
body-s        15 px / Manrope 400        caption
eyebrow       12-13 px / Manrope 700 + 0.16em tracking, uppercase
```

**Serif is the editorial signature — reserve it for display moments.**
Cover hero, section title, the one `stat_callout` number, KPI values, and
pull-quotes use Source Serif 4. Content-slide titles and all body text
use Manrope. Italic Source Serif is the accent treatment for pull-quotes.

## Discipline Rules (non-negotiable)

These separate a generic deck from a boardroom-ready one.

1. **Cobalt Signal is the spine.** Covers and section dividers anchor on
   cobalt (or the dark ink poster). Content slides use cobalt as the one
   accent. If an accent colour starts to dominate, swap it for cobalt or
   ink.
2. **Every slide needs a visual element.** Chart, big number, KPI tile,
   shape, or the brand-mark. Text-only slides are forgettable.
3. **One headline number per deck.** Pick the single most important
   metric for the `stat_callout` (cobalt serif). Every other number lives
   in a `kpi_grid`, table, or chart.
4. **NEVER use accent lines under titles.** The eyebrow + dash *above*
   the title IS the one accent line. Lines under titles are the hallmark
   of AI-generated decks.
5. **No gradient colour backgrounds on content.** The only gradient in
   the system is the cover/closing orb, drawn automatically. Content
   surfaces are solid.
6. **Tabular numerals everywhere numbers stack.** The tool sets this in
   both HTML and PPTX for value columns and KPI blocks.
7. **Captions matter.** Every chart / KPI / stat slide ends with a
   one-line caption naming scope, period, and one interpretation.
8. **The palette must feel designed for THIS topic.** If swapping colours
   into a different deck would still "work", the choice wasn't specific
   enough.
9. **Brand-mark in moderation.** Cover, section dividers, and closing get
   the brand-mark + wordmark; every other slide trusts the chrome
   (eyebrow + dash + page number + small mark) to carry the brand.

## Chart Palette (legend order)

When the tool assigns colours to chart series, this is the order:

1. `254BB2` cobalt Signal — lead
2. `DF9B44` amber — supporting
3. `2695AC` cyan — supporting
4. `913F82` magenta — accent
5. `85B0FF` light cobalt — accent
6. `52657A` slate — neutral / "rest"

≤6 series per chart. Beyond that the palette runs out — split into
multiple charts or use a stacked treatment.

## Backgrounds

| `bg` value | Fill | Text | Accent (eyebrow/dash) | Use |
|---|---|---|---|---|
| `paper` (default) | white `#FFFFFF` | ink-900 | cobalt | content slides |
| `cream` | warm `#FBF0E4` | ink-900 | cobalt | quotes, breathers |
| `signal` | cobalt `#17368D` | white | **amber** | section dividers, solid covers |
| `ink` | near-black `#010204` | ink-100 | **amber** | covers, closings, dramatic charts |

On dark backgrounds (`signal` / `ink`) the eyebrow + dash turn **amber**,
chart axes + legends turn white, and the orb (cover/closing) appears.

## Sizing Budget

- Slide canvas: **1920 × 1080 px** (everything inside `overflow: hidden`)
- Standard padding: **72 px top, 96 px sides, 120 px bottom** (room for
  the page number)
- Section gutter: **24–48 px** between major blocks
- Card padding: **32 px**
- Anything that doesn't fit in 1080 px → split into two slides

## Common Pitfalls

- **Don't repeat the same slide type** — `kpi_grid` × 5 reads as filler.
  Vary `stat_callout` → `chart` → `kpi_grid` → `two_column` → `quote`.
- **Don't center body text** — left-align lists and ledes. Center only
  big-stat values, pull-quotes, and cover/closing titles.
- **Don't put more than one display-size number per slide.**
- **Don't put the brand-mark on every content slide** — it's automatic on
  cover/dividers/closing; content slides trust the eyebrow + dash.
- **Don't set serif on body text** — serif is for display moments only.
- **Don't dump 12-digit numbers** — use K/M/B suffixes on display values.
  Tables and chart axes can stay precise.

## When the user asks for a non-default brief

The tool defaults to the RA Signal system. If the user says:

- **"Make it monochrome"** → drop the amber/cyan/magenta accents; use
  cobalt + ink only. Keep every slide on `paper` and avoid multi-series
  charts that would pull in accent colours.
- **"Go all-dark"** → set `bg:"ink"` on more slides; charts auto-switch
  to white axes. Keep contrast in mind for captions.
- **"Match {external brand}"** → that's a larger change. Ask for the
  primary hex; a one-off deck can use it as the accent, but the RA
  brand-mark + wordmark should be removed for a non-RA deliverable.

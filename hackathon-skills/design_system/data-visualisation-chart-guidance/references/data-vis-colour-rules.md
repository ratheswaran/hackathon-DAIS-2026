# Data Visualisation Colour Rules

> **Single source of truth: `../../tokens.css`** (reconciled RA-editorial). This
> file restates the data-vis colour rules in terms of those tokens. The engine
> (`compose_infographic`) applies them automatically — you do not pass colours.
> ⚠ Any prior bright-red / lavender / health-app series palette is REMOVED —
> those legacy brand colours must not be used in the hackathon's RA-branded
> stories. Use only the `tokens.css` values below.

## Scope

- Light theme only — warm-neutral editorial canvas (`--paper #FAF6EE` / `--oat #F5EFE3`).
- Use the `tokens.css` data-vis tokens and their exact hex values.
- The subject (people's access to care) is serious: muted, no bright reds, no rainbow scales.

## Default single-series colour

General single-series charts use the brand primary:

- `--signal` = **`#254BB2`** (cobalt). Lead line, single-category bars, the series that carries the message.

## Neutral supporting colour

For tracks, backgrounds, and de-emphasized comparison items:

- `--grey` = **`#C7C2B6`**. Also the default for **every series that is NOT the highlighted one** (see "Highlight-by-colour" below).

## Categorical sequence

For multi-category charts, apply colours in this exact order (mirrors `_SERIES` in
the engine):

1. `--signal`  = `#254BB2` (cobalt)
2. `--amber`   = `#DF9B44`
3. `--cyan`    = `#2695AC`
4. `--magenta` = `#913F82`
5. `--slate`   = `#3A3A40`
6. `--mute`    = `#9CA0A3`
7. `Others`    = `--grey` `#C7C2B6` (aggregate the remainder)

Rules:
- Apply strictly left to right.
- For more than 6 distinct categories, aggregate the remainder as `Others` (`--grey`).
- Keep the sequence stable across related charts on the same page when categories match.

## Highlight-by-colour (the default storytelling mode)

Most series render **neutral `--grey`**; only the entity the prose names gets an
accent (`--signal`, or `--amber` on dark backgrounds). Set `scene.highlight` to that
entity. This is why the eye lands where the sentence points — prefer it over giving
every series its own colour.

## Ordered / sequential & diverging palettes

Use a colour *ramp* only when the meaning is genuinely ordered (rate, magnitude band,
risk, progress) — never for arbitrary categories.

- **Sequential**: a single-hue light→dark **cobalt** ramp (`#EaF0Fb` → `#254BB2`). Used by
  the choropleth + heatmap. Lightness/saturation are perceptually ordered; hue is not.
- **Diverging**: only when the measure crosses a *meaningful midpoint* (e.g. a deviation
  around 0) — amber ↔ cobalt with a pale middle. Never red↔green (colour-blind unsafe).
- Where colour encodes a number AND precision matters (the matrix), **print the number in
  the cell** — colour is a low-rank perceptual channel (Cleveland–McGill), so it's secondary.

## What to avoid

- No rainbow / saturated palettes; no bright reds (subject is serious).
- No semantic UI colours as a default chart palette.
- No 3-D, no pie/donut (low-rank angle/area encodings) — use `ranked_bar` / `kpi_grid`.
- No randomised category-colour order; keep the sequence stable.
- No colour tokens or hexes outside `tokens.css`.
- Don't rely on colour alone to distinguish categories — pair with label/position
  (~8% of men have a colour-vision deficiency).

---
name: compose-pptx
description: >
  Build presentation decks via the `compose_deck` tool. Use whenever the
  user asks for slides, a deck, a presentation, or a .pptx briefing. The
  tool consumes ONE JSON deck spec and produces an editable PPTX (with
  native PowerPoint charts) plus an HTML preview. Resonance Analytics
  brand baked in (cobalt "Signal" + Source Serif 4 / Manrope).
---

# Compose Deck — Resonance Analytics

## Quick Reference

| Task | Where to read next |
|------|-------------------|
| First deck this session | Read [spec_reference.md](spec_reference.md) — the full slide-type and chart-type cookbook |
| Need a layout you haven't seen | `read_file("/skills/compose-pptx/design_system_deck_example.html")` — the canonical 36-slide RA design deck has every pattern |
| User asked for a specific visual brief (non-default colours / mono / monochrome) | Read [design.md](design.md) for the palette + type tokens |
| Already wrote a deck this session — write another | Skip these reads, go to **Tool Signature** |

Most prompts only need `spec_reference.md` once per session. `design.md`
is only needed for a non-default brief. The defaults (Resonance Analytics
cobalt **Signal**, Manrope + Source Serif 4, 1920×1080) are right for
almost every deck.

## When to Use

User mentions any of: **deck · slides · presentation · PowerPoint ·
.pptx · executive summary · board slides · client pitch · readout**.

The agent's authoring surface is **a JSON deck spec**, not HTML and not
python code. The tool renders the spec into PPTX with native PowerPoint
charts (editable bars/lines/pies) and an HTML preview from the same
source of truth.

Never improvise via `run_python_code` — that container has no UC volume
mount, so writes to `/Volumes/...` go to tmpfs and are silently lost.
`compose_deck` uploads through the Files API so the bytes actually land
in Unity Catalog and can be served back through the app.

> `compose_deck` replaces the old `compose_document` *pptx* path for
> presentation decks. `compose_document` still handles **docx / xlsx /
> csv / pdf**; for anything that is "slides", use `compose_deck`.

## Brand at a glance

Resonance Analytics — "Boardroom Editorial". Corporate, precise, data-forward.

- **Primary:** cobalt-indigo **Signal** `#254BB2`. Dominant on covers,
  section dividers, table headers, chart leads, accents.
- **Neutrals:** cool-slate **ink** (`#050A0F` text → `#F9FAFC` paper).
- **Accents (harmonized):** amber `#DF9B44`, cyan `#2695AC`, magenta `#913F82`.
- **Type:** Manrope (sans — UI, body, titles) + Source Serif 4 (display —
  covers, hero numbers, section openers, pull-quotes) + JetBrains Mono
  (page numbers, small data). Serif is the editorial signature; use it
  only for display moments.
- **Signature:** the dark **cover poster** — a near-black field with a
  glowing cobalt orb + amber rim. The renderer draws it automatically.
- **No raster logos.** The RA brand-mark (a cobalt rounded square + a
  small cross-hair) and the "Resonance Analytics" wordmark are drawn
  natively onto cover / section / closing slides. There is no `logo`
  field — don't add one.

## Tool Signature

```python
compose_deck(
    title: str,         # required — used for filename + cache key
    deck_spec: list,    # required — list of slide dicts. See spec_reference.md.
) -> JSON
```

### Return shape

```json
{
  "status": "ok",
  "document_id": "deck_<12hex>",
  "title": "...",
  "slide_count": 8,
  "preview_url": "<app>/api/decks/deck_<12hex>",
  "pptx_url":    "<app>/api/decks/deck_<12hex>.pptx",
  "volumes_path": "/Volumes/workspace/ai_ops/agent_scratch/documents/<id>__<slug>.{pptx,html,json}",
  "size_bytes":  {"pptx": 62619, "html": 20173}
}
```

`preview_url` / `pptx_url` are present whenever `APP_URL` is configured
(always true in the deployed app). The artifacts always land on the
volume, so `volumes_path` is always returned.

**Always surface BOTH URLs to the user.** They pick:

- `pptx_url` — editable PowerPoint with NATIVE charts (bars / lines /
  pies are editable PowerPoint chart objects, not screenshots). Export
  to PDF from PowerPoint if a PDF is needed.
- `preview_url` — HTML render of the deck for in-browser preview before
  downloading.

**Quote them verbatim.** Never fabricate a URL.

### Errors

`{"status":"error", "code":"<reason>", "message":"<one-liner>"}`.

| Code | Meaning | Fix |
|------|---------|-----|
| `empty_title` / `empty_spec` | required arg missing | retry with both |
| `no_slides` | deck_spec was empty list | add slides |
| `invalid_slide_type` | a slide has an unrecognized `type` | use one of the types in spec_reference.md |
| `invalid_chart_type` | a chart slide has an unrecognized `chart` | use bar / column / line / pie |
| `render_failed` | python-pptx raised | check shape of offending slide; the message names the slide index |
| `upload_failed` | Files API rejected the put | rare; ping operator about UC grants |

Adjust the spec before retrying. **Never retry the same call twice with
identical args.** Two retries max per turn.

## Hard Rules (non-negotiable)

1. **Use this tool — not `run_python_code`** for any deck output.
2. **Every deck has a cover + at least one content slide.**
3. **Never fabricate URLs.** Quote the tool's return verbatim.
4. **Count slides honestly.** Report `slide_count` to the user.
5. **No placeholder content.** "TBD", "Lorem ipsum", "Insert content
   here" — never ship.
5a. **Stop querying once you have the numbers. Inline-format them in the
   spec.** After a query returns the raw values you need, do NOT chain
   more queries to pre-format them into K/M/B strings or rounded
   decimals. Write the formatted string directly:
   `"value": "17", "unit": "x lower"`. One or two queries per deck is
   normal; ten queries means you are over-engineering.
5b. **Cover + closing + section titles: keep them short** (≤ 8 words,
   fits two lines). Push period/scope/preparer detail into `lede`.
   Example: title `"The Asylum Lottery"` + lede `"Why identical claims
   meet opposite fates across Europe."` — not a period crammed into the
   title.
6. **Data unavailable → build the deck anyway with the closest available
   data.** After one attempt that confirms absence, pivot. The first
   content slide MUST then be a `data_note` naming the requested vs the
   substituted scope and the reason. Reaching the loop guard without
   ever calling `compose_deck` is a worse failure than admitting a gap.
7. **Don't retry on `render_failed` with the same spec.** Strip the
   offending slide and re-call.

## Design Ideas

**Don't create boring slides.** Plain bullets on white won't impress.
The defaults are RA-branded — but the *composition* still has to earn it.

### Before Starting

- **Signal cobalt is the spine.** Covers, section dividers, table
  headers, and the lead chart series are cobalt. If a secondary colour
  (amber / cyan / magenta) starts to dominate, pull it back.
- **Commit to the chrome motif.** The eyebrow + dash above the title,
  the cobalt accent tick, the brand-mark + page number — carry them
  across every slide. They ARE the brand presence; you don't need a
  logo on every slide.
- **Sandwich dark + light.** Open with an `ink` cover (cobalt orb),
  close with an `ink` closing; section dividers can go `signal`
  (cobalt). Content slides stay light (`paper` / `cream`).
- **Serif is for display only.** Cover hero, section title, the one
  hero number (`stat_callout`), KPI values, and pull-quotes get Source
  Serif 4. Content-slide titles and all body text are Manrope.

### For Each Slide

**Every slide needs a visual element** — chart, big number, KPI grid,
brand-mark, or shape. Text-only slides are forgettable.

**Slide-type catalogue (use varied layouts, never repeat):**

| Type | Best for |
|------|---------|
| `cover` | First slide; deck title + lede (dark cobalt-orb poster) |
| `section_divider` | Open a new act ("Findings", "Risks", "Recommendations") |
| `stat_callout` | Single hero number — the deck's headline metric (cobalt serif) |
| `kpi_grid` | 3-4 supporting metrics in tiles |
| `bullets` | Plain content with title + lede + bullet list (use sparingly) |
| `two_column` | Pros/cons, before/after, "what's working / at risk" |
| `chart` | Native PowerPoint bar/column/line/pie with data labels |
| `chart_commentary` | Chart + sidebar of 3-4 short observations |
| `table` | Tabular data ≤6 rows × ≤5 cols |
| `quote` | Pull-quote (Source Serif italic) |
| `data_note` | Period / scope substitution or data caveat |
| `timeline` | Process steps or milestone progression |
| `closing` | Final slide; thank-you / next-steps / CTA |

**Chart-type selection:**

| Pattern in data | Use |
|----------------|-----|
| Ranking N items (N ≤ 7) | **column** (vertical bars). Sort descending; lead series in cobalt |
| Ranking many items (N > 7) | **bar** (horizontal bars). Easier to label |
| Trend over time | **line** with markers on points |
| Composition / share of total | **pie** ONLY if ≤5 segments. Otherwise a stacked column. Show percentages |
| Two metrics over the same categories | **column** with two series |

≤6 series per chart. Beyond that the palette runs out — split into
multiple charts or use a stacked treatment.

### Avoid (Common Mistakes)

- **Don't repeat the same layout** — vary `stat_callout`, `chart`,
  `kpi_grid`, `two_column`, `quote` across the deck.
- **Don't center body text** — left-align lists; center only big-stat
  values, pull-quotes, and cover/closing titles.
- **Don't put more than one display-size number per slide** — pick ONE
  headline (`stat_callout`); everything else is a `kpi_grid` or chart.
- **NEVER use accent lines under titles** — the eyebrow + dash *above*
  the title IS the one accent line. Lines under titles are the hallmark
  of AI-generated decks.
- **No text-only slides** — every slide gets a chart, KPI tile, big
  number, or shape.
- **Don't over-explain the chart in the title.** The title says what
  the data says ("Germany recognises 96%, Sweden 40%"), not what kind of
  chart it is ("Bar chart of recognition rate").
- **Don't add a `logo` field.** The brand-mark is drawn automatically.

## QA (Required)

**Assume there are problems. Your job is to find them.**

After every `compose_deck` call:

1. **Re-read your `deck_spec`.** Look for: empty strings, "TBD", numbers
   that don't match the source data, captions that contradict the chart,
   missing periods.
2. **Mention the `preview_url`** so the user can spot-check on screen
   before downloading.
3. **If anything looks off**, build a corrected spec and call
   `compose_deck` again. The id is keyed on (title, spec) so a new spec
   gets a new id.

Stay within the iteration budget. Every avoidable `read_file` is one
fewer round for data / the actual compose call.

## Authoring rhythm

1. Pull data (Genie / SQL / stored DFs). Know the headline number.
2. Plan content → outline 4-8 slides in your head.
3. If first deck this session: read [spec_reference.md](spec_reference.md).
   If user asked for a non-default visual brief: also read [design.md](design.md).
4. Compose the full `deck_spec` list.
5. Call `compose_deck(title=..., deck_spec=[...])` once.
6. Surface both URLs.

## Fonts (one-time note)

Manrope + Source Serif 4 are referenced by name. The **HTML preview**
loads them from Google Fonts and is always pixel-faithful. In
**PowerPoint** they render faithfully *if the fonts are installed* on
the viewer's machine; otherwise PowerPoint substitutes, preserving the
sans/serif contrast. For board-ready exports, install both fonts (free,
Google Fonts) before exporting to PDF.

## Template (optional)

By default the renderer paints the full RA brand chrome itself
(from-scratch mode) — no template needed. To brand from a designed
PowerPoint template instead, drop it at
`/skills/compose-pptx/templates/ra_template.pptx`. See
[templates/README.md](templates/README.md) for the required layout names.

## Dependencies (provisioned)

Already wired up — listed for reference, not for you to install:

- python-pptx (PPTX render, native charts) — already in `requirements.txt`

# Resonance Analytics PPTX template

`ra_template.pptx` **ships in this folder** — so `compose_deck` template mode is
**ON by default** for the next deploy. The renderer paints only *content* on top
of this template's master + layouts; backgrounds, the cobalt-orb cover, the
brand-mark/wordmark, footers and page numbers all come from the template.

Built reproducibly by **`build_ra_template.py`** (next to this file) with
python-pptx, embedding the brand assets in `../assets/`. It then calls
**`embed_fonts.py`** to embed the brand fonts from `../assets/fonts/`. To rebuild
after an asset, layout, or font tweak:

```bash
cd hackathon-skills/compose-pptx/templates
python3 build_ra_template.py        # rewrites ra_template.pptx + embeds fonts
# (embed_fonts.py also runs standalone on any .pptx if you need it)
```

## Resolution order (how the tool finds it)

`compose_deck` picks its base template in this order (first hit wins):

1. `template_path=` passed to `build_compose_deck_tool(...)` (explicit)
2. `COMPOSE_DECK_TEMPLATE` env var — an absolute path, **or** `""`
   (empty string) to **force from-scratch mode** and ignore the bundled file
3. the bundled `templates/ra_template.pptx` (this folder) — **present now**
4. otherwise → from-scratch mode

> The orchestrator's `skills/` dir is a symlink to `hackathon-skills/`, so at
> runtime the tool sees this at
> `…/hackathon-orchestrator/skills/compose-pptx/templates/ra_template.pptx`.
> When a template is active the tool logs `[compose_deck] template mode ON,
> template=…` at WARNING level.

To go back to the renderer-drawn chrome, set `COMPOSE_DECK_TEMPLATE=""` (or
delete this file). From-scratch mode is fully supported and needs no template.

## What's inside (the seven layouts the renderer looks up by name)

Chrome wordmark = the **official RA logo lockup** (the "reso" radial mark +
"Resonance Analytics" in Manrope), `ra-lockup-dark.png` on dark / `-light.png`
on light. The brand fonts (Source Serif 4 / Manrope / JetBrains Mono) are
**embedded** in the file.

| Layout | Used for | Renderer fills | Chrome the layout supplies |
|---|---|---|---|
| `RA_TitleSlide` | cover (slide 1, the kept seed slide) | placeholder **idx 10** = title (Source Serif), **idx 1** = subtitle | full-bleed `cover-poster.png` orb, logo lockup top-left, page number |
| `RA_thankyou` | the `closing` slide | **idx 11** = title, **idx 1** = subtitle | near-black fill, logo lockup top-left, amber `geomark` bottom-right, page number |
| `RA_blank` | every light content slide (default) | content painted on top | **pure white** (`#FFFFFF`) fill, footer lockup + page number |
| `RA_cream` | content with `bg:"cream"` (quotes, data-notes) | content painted on top | warm cream (`#FBF0E4`) fill, footer lockup + page number |
| `RA_dark` | content with `bg:"ink"` / `"charcoal"` / `"dark"` | content on top | near-black fill, white footer lockup + page number |
| `RA_SectionSignal` | `section_divider` with `bg:"signal"` | eyebrow + serif title + lede | solid cobalt (`#17368D`) fill, logo lockup top-left, footer |
| `RA_SectionWhite` | `section_divider` with `bg:"paper"`/`"white"` | eyebrow + serif title + lede | **subtle blue** (`#F9FAFC`, the design-system paper) fill, ink lockup top-left, footer |

Placeholders idx 10/11/1 are the renderer's hard contract — the builder
re-stamps them and **deletes the stock Date(10)/Footer(11)/SlideNumber(12)
placeholders** that python-pptx ships, which would otherwise collide with the
title indices. Content/section layouts carry **zero** content placeholders (the
renderer paints everything and strips empties).

## Verified

Built + smoke-tested end-to-end through the real `compose_deck._render_pptx` in
template mode (a 14-slide deck exercising every slide type, incl. `bg:"cream"`),
then rasterised (LibreOffice → `pdftoppm`) and run through a 4-lens adversarial
visual QA (brand · typography · logo · layout) — **zero confirmed defects**.
Background pixels sampled exact: `RA_blank` `#FFFFFF`, `RA_SectionWhite`
`#F9FAFC`, `RA_cream` `#FBF0E4`. Fonts are right (Manrope sans for titles/body;
Source Serif 4 for the cover, section, closing, the one big stat, KPI values,
and pull-quotes; JetBrains Mono page numbers) **and embedded** — an XML audit
confirms the rendered deck still carries all 9 font parts + `embedTrueTypeFonts`.
Package is structurally clean (image rels resolve → opens without a repair
prompt). Re-run that smoke test any time:

```python
import sys; sys.path.insert(0, "hackathon-orchestrator")
from tools.compose_deck import _render_pptx
open("/tmp/smoke.pptx","wb").write(
    _render_pptx("Smoke", [{"type":"cover","title":"Hi","lede":"…"}],
                 template_path="hackathon-skills/compose-pptx/templates/ra_template.pptx"))
```

## Known limitations (inherent to template mode)

1. **Page numbers show the current slide only** (e.g. `7`), not the renderer's
   `07 / 13`. Template mode suppresses the renderer's footer, and a PowerPoint
   `slidenum` field can't render a deck total. Cosmetic; the number is correct.
2. **`bg:"signal"` is section-divider only.** A *content* slide with
   `bg:"signal"` routes to `RA_blank` (white) — and the renderer would paint
   white text on it. **Use `bg:"signal"` only on `section_divider`**; for dark
   *content* use `bg:"ink"` (→ `RA_dark`). (Fixed since the cream/blue pass:
   `bg:"cream"` now routes to its own `RA_cream` layout — it no longer renders
   on white — and `RA_SectionWhite` carries the subtle-blue `#F9FAFC` paper.)
3. **Cover + closing use the top-left logo lockup, no footer lockup** — by
   design, matching the from-scratch hero treatment. Content/section slides
   carry the lockup in the footer.
4. **Fonts are EMBEDDED** (Source Serif 4 / Manrope / JetBrains Mono, full faces,
   all SIL OFL) via `embed_fonts.py`, so the serif + mono render even on machines
   without them installed. The embedded-font parts + `<p:embeddedFontLst>` are
   re-built by `build_ra_template.py` and **survive the python-pptx load+save**
   in `compose_deck` template mode (verified), so rendered decks inherit them.
   The definitive pixel check is still opening in real PowerPoint.
5. **Canvas is `Inches(13.333)` = 12,191,695 EMU** (not the round 12,192,000) —
   chosen deliberately to match `compose_deck`'s own `SLIDE_W_IN = 13.333`
   coordinate system exactly, so painted content aligns to the template edges.

## If you hand-edit the template in PowerPoint

You can open `ra_template.pptx`, tweak the master/layouts (Slide Master view),
and save — just **keep the seven layout names and the idx 10/11/1 placeholders**
intact, or `build_ra_template.py` is the source of truth to regenerate from.
(Hand-editing in PowerPoint and re-saving may drop the embedded fonts; re-run
`embed_fonts.py ra_template.pptx` afterwards, or just rebuild.)

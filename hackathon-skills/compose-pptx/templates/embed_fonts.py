#!/usr/bin/env python3
"""Embed the RA brand fonts into a .pptx so they travel with the file.

Why this exists
---------------
python-pptx sets the theme major/minor fonts (Source Serif 4 / Manrope) and the
renderer tags runs with explicit typefaces (incl. JetBrains Mono on page
numbers), but python-pptx **cannot embed font binaries**. On a machine without
those fonts installed, PowerPoint substitutes — which is why a deck can look
"all Manrope" (or all-substitute). This injects the actual TrueType data as
PowerPoint embedded-font parts so the serif + mono render everywhere.

What it writes (the OOXML embedded-font contract):
  * ``ppt/fonts/fontN.fntdata`` parts holding the raw TTF bytes
  * a ``Default Extension="fntdata"`` content-type
  * a ``.../relationships/font`` relationship per part from the presentation
  * ``<p:embeddedFontLst>`` in presentation.xml (correct schema slot: right
    after ``<p:notesSz>``) + ``embedTrueTypeFonts="1"`` on ``<p:presentation>``

Fonts are full (not subset) → ``saveSubsetFonts`` is left off. All three
families are SIL OFL, which permits embedding. The bundled TTFs live in
``../assets/fonts``.

Round-trip note: compose_deck renders in template mode via
``Presentation(template).save()``. These parts/relationships/elements are
preserved across that python-pptx load+save (verified), so rendered decks
inherit the embedded fonts from the template — no render-time step needed.

Run:  python3 embed_fonts.py [in.pptx] [out.pptx]   # defaults to the template
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(HERE, "..", "assets", "fonts")
DEFAULT_PPTX = os.path.join(HERE, "ra_template.pptx")

# Namespaces
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
FONT_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"

# typeface -> {style: ttf filename}. Styles emitted in schema order:
# regular, bold, italic, boldItalic. Manrope ships no italic.
FONT_MAP = {
    "Playfair Display": {
        "regular": "PlayfairDisplay-Regular.ttf", "bold": "PlayfairDisplay-Bold.ttf",
        "italic": "PlayfairDisplay-Italic.ttf", "boldItalic": "PlayfairDisplay-BoldItalic.ttf",
    },
    "Manrope": {
        "regular": "Manrope-Regular.ttf", "bold": "Manrope-Bold.ttf",
    },
    "JetBrains Mono": {
        "regular": "JetBrainsMono-Regular.ttf", "bold": "JetBrainsMono-Bold.ttf",
        "italic": "JetBrainsMono-Italic.ttf",
    },
}
_STYLE_ORDER = ["regular", "bold", "italic", "boldItalic"]


def _qp(tag: str) -> str:
    return f"{{{P}}}{tag}"


def _next_rid(rels_root) -> int:
    mx = 0
    for rel in rels_root:
        rid = rel.get("Id", "")
        if rid.startswith("rId") and rid[3:].isdigit():
            mx = max(mx, int(rid[3:]))
    return mx + 1


def embed_fonts(src_pptx: str, dst_pptx: str, fonts_dir: str = FONTS_DIR) -> dict:
    with zipfile.ZipFile(src_pptx, "r") as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}

    # --- gather font bytes + assign part names/rels ------------------------
    rels_root = etree.fromstring(data["ppt/_rels/presentation.xml.rels"])
    rid = _next_rid(rels_root)
    font_parts = []          # (part_path, ttf_bytes)
    embedded = []            # (typeface, {style: rId})
    fidx = 1
    for typeface, styles in FONT_MAP.items():
        style_rids = {}
        for style in _STYLE_ORDER:
            fname = styles.get(style)
            if not fname:
                continue
            ttf_path = os.path.join(fonts_dir, fname)
            with open(ttf_path, "rb") as fh:
                blob = fh.read()
            part = f"ppt/fonts/font{fidx}.fntdata"
            rId = f"rId{rid}"
            rel = etree.SubElement(rels_root, f"{{{PR}}}Relationship")
            rel.set("Id", rId)
            rel.set("Type", FONT_RT)
            rel.set("Target", f"fonts/font{fidx}.fntdata")
            font_parts.append((part, blob))
            style_rids[style] = rId
            rid += 1
            fidx += 1
        embedded.append((typeface, style_rids))
    data["ppt/_rels/presentation.xml.rels"] = etree.tostring(
        rels_root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # --- content types: one Default for the fntdata extension --------------
    ct_root = etree.fromstring(data["[Content_Types].xml"])
    has_default = any(
        d.get("Extension") == "fntdata" for d in ct_root
        if d.tag == f"{{{CT}}}Default")
    if not has_default:
        d = etree.SubElement(ct_root, f"{{{CT}}}Default")
        d.set("Extension", "fntdata")
        d.set("ContentType", "application/x-fontdata")
    data["[Content_Types].xml"] = etree.tostring(
        ct_root, xml_declaration=True, encoding="UTF-8", standalone=True)

    # --- presentation.xml: embedTrueTypeFonts + <p:embeddedFontLst> --------
    pres = etree.fromstring(data["ppt/presentation.xml"])
    pres.set("embedTrueTypeFonts", "1")
    # remove any pre-existing list so re-runs are idempotent
    for old in pres.findall(_qp("embeddedFontLst")):
        pres.remove(old)
    lst = etree.SubElement(pres, _qp("embeddedFontLst"))
    for typeface, style_rids in embedded:
        ef = etree.SubElement(lst, _qp("embeddedFont"))
        f = etree.SubElement(ef, _qp("font"))
        f.set("typeface", typeface)
        for style in _STYLE_ORDER:
            if style in style_rids:
                s = etree.SubElement(ef, _qp(style))
                s.set(f"{{{R}}}id", style_rids[style])
    # move embeddedFontLst into its schema slot: CT_Presentation requires it
    # right after <p:notesSz> (… sldIdLst, sldSz, notesSz, embeddedFontLst …).
    # NB: use explicit `is not None` — an empty element like <p:notesSz/> is
    # falsy under lxml's (deprecated) element truth-testing, so an `or`-chain
    # would skip it and misplace the list before sldSz.
    pres.remove(lst)
    anchor = None
    for tag in ("notesSz", "sldSz", "sldIdLst"):
        el = pres.find(_qp(tag))
        if el is not None:
            anchor = el
            break
    if anchor is not None:
        anchor.addnext(lst)
    else:
        pres.append(lst)
    data["ppt/presentation.xml"] = etree.tostring(
        pres, xml_declaration=True, encoding="UTF-8", standalone=True)

    # --- write the new package --------------------------------------------
    for part, blob in font_parts:
        data[part] = blob
    tmp = dst_pptx + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n, blob in data.items():
            z.writestr(n, blob)
    shutil.move(tmp, dst_pptx)
    return {"fonts": fidx - 1, "families": list(FONT_MAP)}


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PPTX
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    info = embed_fonts(src, dst)
    print(f"embedded {info['fonts']} font files for {info['families']} -> {dst}")


if __name__ == "__main__":
    main()

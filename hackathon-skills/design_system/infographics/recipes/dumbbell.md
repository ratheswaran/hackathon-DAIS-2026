# Recipe — dumbbell

**Data shape** (`scene.data`):
d = {
  left:  [ {key, name, rank, value, value_fmt?, standout?} ... ],   // metric-A column, rank 1 = top, ascending
  right: [ {key, name, rank, value, value_fmt?, standout?} ... ],   // metric-B column
  movers:[ {key, dir} ... ],   // entities present on BOTH columns; dir 'up' (rises on B, amber) | 'down' (falls, cyan). Connector drawn between their lRank and rRank.
  left_head, right_head:  string column headers (rendered uppercased)
  left_sub?, right_sub?:  optional small sub-headers (e.g. 'rank 1 = most facilities')
  annotations?: [ {side:'left'|'right', rank, text} ... ]   // italic-serif callouts anchored beside a row, offset 15px above
}
Notes: `key` joins left↔right↔movers (e.g. a district id). `value` is numeric (formatted via H.fmt unless `value_fmt` given, e.g. '1,480', '78.4'). `standout:true` accents a row that appears on only ONE column (e.g. high-burden-only / high-coverage-only). `scene.highlight` (name or key, or array) overrides to accent any entity; otherwise movers=amber(up)/cyan(down), everything else grey.

**Minimal sample** (`scene.data`):
```json
{
  "left_head": "By facility count",
  "left_sub": "rank 1 = most facilities",
  "right_head": "By health-burden index",
  "right_sub": "rank 1 = highest burden",
  "left": [
    {
      "key": "LKO",
      "name": "Lucknow",
      "rank": 1,
      "value": 210,
      "value_fmt": "210",
      "standout": true
    },
    {
      "key": "PAT",
      "name": "Patna",
      "rank": 2,
      "value": 168,
      "value_fmt": "168"
    },
    {
      "key": "IDR",
      "name": "Indore",
      "rank": 3,
      "value": 140,
      "value_fmt": "140"
    },
    {
      "key": "PNE",
      "name": "Pune",
      "rank": 4,
      "value": 198,
      "value_fmt": "198"
    },
    {
      "key": "CHN",
      "name": "Chennai",
      "rank": 5,
      "value": 260,
      "value_fmt": "260"
    },
    {
      "key": "JAI",
      "name": "Jaipur",
      "rank": 6,
      "value": 155,
      "value_fmt": "155"
    },
    {
      "key": "BPL",
      "name": "Bhopal",
      "rank": 7,
      "value": 132,
      "value_fmt": "132"
    },
    {
      "key": "ARA",
      "name": "Araria",
      "rank": 8,
      "value": 4,
      "value_fmt": "4"
    }
  ],
  "right": [
    {
      "key": "ARA",
      "name": "Araria",
      "rank": 1,
      "value": 78.4,
      "value_fmt": "78.4",
      "standout": true
    },
    {
      "key": "KIS",
      "name": "Kishanganj",
      "rank": 2,
      "value": 74.1,
      "value_fmt": "74.1"
    },
    {
      "key": "SRW",
      "name": "Shrawasti",
      "rank": 3,
      "value": 71.8,
      "value_fmt": "71.8"
    },
    {
      "key": "PAT",
      "name": "Patna",
      "rank": 4,
      "value": 44.2,
      "value_fmt": "44.2"
    },
    {
      "key": "BPL",
      "name": "Bhopal",
      "rank": 5,
      "value": 41.6,
      "value_fmt": "41.6"
    },
    {
      "key": "JAI",
      "name": "Jaipur",
      "rank": 6,
      "value": 38.9,
      "value_fmt": "38.9"
    },
    {
      "key": "BRW",
      "name": "Barwani",
      "rank": 7,
      "value": 66.4,
      "value_fmt": "66.4"
    },
    {
      "key": "NDB",
      "name": "Nandurbar",
      "rank": 8,
      "value": 63.9,
      "value_fmt": "63.9"
    }
  ],
  "movers": [
    {
      "key": "PAT",
      "dir": "down"
    },
    {
      "key": "BPL",
      "dir": "down"
    },
    {
      "key": "JAI",
      "dir": "down"
    },
    {
      "key": "ARA",
      "dir": "up"
    }
  ],
  "annotations": [
    {
      "side": "left",
      "rank": 1,
      "text": "most facilities — yet low on the burden ranking"
    },
    {
      "side": "right",
      "rank": 1,
      "text": "highest burden — yet near the bottom for facilities"
    }
  ]
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
    # Build a dumbbell/slope between two ranked metrics that share a join key.
    # mapping: {key_col, name_col, a_col (metric A), b_col (metric B),
    #           top_n?, a_head?, b_head?, a_sub?, b_sub?,
    #           a_scale?(divide A, e.g. 1e6), b_round?(dp for B)}
    mp = mapping or {}
    key_c = mp.get("key_col") or mapping.get("name_col") or df.columns[0]
    name_c = mp.get("name_col") or key_c
    a_c = mp["a_col"]; b_c = mp["b_col"]
    top_n = int(scene.get("top_n", mp.get("top_n", 12)))
    a_scale = float(mp.get("a_scale", 1) or 1)
    b_dp = mp.get("b_round")

    sub = df.copy()
    sub[a_c] = pd.to_numeric(sub[a_c], errors="coerce")
    sub[b_c] = pd.to_numeric(sub[b_c], errors="coerce")

    a_sorted = sub.dropna(subset=[a_c]).sort_values(a_c, ascending=False).head(top_n).reset_index(drop=True)
    b_sorted = sub.dropna(subset=[b_c]).sort_values(b_c, ascending=False).head(top_n).reset_index(drop=True)

    def _afmt(v):
        return f"{v/a_scale:.2f}M" if a_scale >= 1e6 else (f"{v:,.0f}" if a_scale == 1 else f"{v/a_scale:.2f}")

    def _bfmt(v):
        return f"{v:.{int(b_dp)}f}" if b_dp is not None else f"{v:.1f}"

    a_keys = {str(r[key_c]): i + 1 for i, r in a_sorted.iterrows()}
    b_keys = {str(r[key_c]): i + 1 for i, r in b_sorted.iterrows()}

    left = [{"key": str(r[key_c]), "name": str(r[name_c]), "rank": i + 1,
             "value": float(r[a_c]), "value_fmt": _afmt(float(r[a_c])),
             "standout": str(r[key_c]) not in b_keys}
            for i, r in a_sorted.iterrows()]
    right = [{"key": str(r[key_c]), "name": str(r[name_c]), "rank": i + 1,
              "value": float(r[b_c]), "value_fmt": _bfmt(float(r[b_c])),
              "standout": str(r[key_c]) not in a_keys}
             for i, r in b_sorted.iterrows()]
    shared = [k for k in a_keys if k in b_keys]
    movers = [{"key": k, "dir": "up" if b_keys[k] < a_keys[k] else "down"} for k in shared]

    return {
        "left": left, "right": right, "movers": movers,
        "left_head": mp.get("a_head", a_c), "right_head": mp.get("b_head", b_c),
        "left_sub": mp.get("a_sub", ""), "right_sub": mp.get("b_sub", ""),
        "annotations": scene.get("annotations", []),
    }
```

**Notes:** PORT FIDELITY: This is the reference's "slope chart between two ranked columns" (the reference builder writes a slope despite the dumbbell filename). Faithfully kept: two vertical axes at xL=370/xR=560, rows by rank (rowH=40, TOP=120), rank ticks in the inner gutter, names+values OUTSIDE each axis (left=anchor end, right=anchor start), connectors ONLY for the 4 shared "movers" drawn behind the dots, italic-serif standout annotations 15px above the named row. Big dots (r6) for movers + standouts, small (r4.5) otherwise.

MOTION: The reference animated connectors via stroke-dashoffset and rows via opacity. Per the contract's non-negotiable rule I dropped stroke-dashoffset — connectors now have FINAL geometry at t=0 and reveal via H.in (opacity) only; rows fade via H.in; annotations fade via H.in with a later delay. A t=0 screenshot shows fully-correct geometry. Partial transparency on connectors uses the stroke-opacity ATTR (.85), not style opacity, so H.in's element-opacity doesn't clobber it.

COLOUR: Default grey (P.grey). Movers get direction colour: up→P.amber, down→P.cyan (the reference used clay/blue; mapped to the engine's amber/cyan accents). scene.highlight (name OR key, string or array) overrides to accent any entity with P.signal. The two hand-picked standouts (e.g. facility-count-only, burden-only) are data-driven here via `standout:true` (or auto-derived in the python_shaper when a key is on only one column).

CSS: Uses only existing classes — axis-title (headers/subs), vlabel (mono rank ticks + numeric value tspans), clabel (entity names), annot (italic-serif findings). No <style> injected. Axis lines use P.hair to match the engine's .axis stroke.

VIEWBOX: 920 wide; height auto-grows with row count (TOP + n*rowH + BOT). Designed for ~12 rows per column like the reference.

DATA: `key` is the join field across left/right/movers (use a district id or the district name). movers MUST list only entities present on BOTH columns; the renderer also filter-guards this (filters movers whose key is missing from either column) so a sloppy spec won't draw a stray connector. value_fmt is preferred for the two different units (facility count vs burden index); falls back to H.fmt.

PYTHON_SHAPER: optional — builds the dict from a long DataFrame with one row per entity carrying both metric columns (a_col, b_col) + a key/name column. It independently top-N-sorts each metric, derives ranks, auto-flags standouts (on only one column) and mover direction. a_scale (e.g. 1e6) controls the M-formatting of metric A; b_round controls metric-B decimals. If the agent precomputes the slice it can pass `data` inline and skip this.

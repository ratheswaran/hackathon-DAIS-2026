# Recipe — bar_race

**Data shape** (`scene.data`):
d = {
  frames: [ { year: <number|string>, rows: [ {label:<str>, value:<number>, color?:<hex>} ] }, ... ],
  top_n?: <number>   // bars shown per frame; default 10 (or scene.top_n)
}
One frame per time step, ordered earliest→latest. Each frame's `rows` is the FULL field for that year (any length); the renderer filters value>0, sorts desc, and slices to top_n, re-ranking per frame so bars reorder.
`color` is optional per-row (e.g. region-bucket colour); if omitted, bars render neutral P.grey and only the entity named in scene.highlight is accented via H.hue.
Scene meta used: scene.highlight (label to accent), scene.value_label (axis-title text), scene.annotations[0] (one italic-serif finding annotation), scene.top_n (fallback for d.top_n).
The LATEST frame is rendered first as the resting state; the loop (if motion allowed) replays earliest→latest and ends back on the latest.

**Minimal sample** (`scene.data`):
```json
{
  "top_n": 6,
  "frames": [
    {
      "year": 2014,
      "rows": [
        {
          "label": "Syria",
          "value": 7600000
        },
        {
          "label": "Afghanistan",
          "value": 4200000
        },
        {
          "label": "Colombia",
          "value": 6100000
        },
        {
          "label": "DR Congo",
          "value": 2900000
        },
        {
          "label": "Somalia",
          "value": 2100000
        },
        {
          "label": "Sudan",
          "value": 1800000
        },
        {
          "label": "Iraq",
          "value": 1500000
        }
      ]
    },
    {
      "year": 2018,
      "rows": [
        {
          "label": "Syria",
          "value": 12600000
        },
        {
          "label": "Afghanistan",
          "value": 4900000
        },
        {
          "label": "Colombia",
          "value": 7900000
        },
        {
          "label": "DR Congo",
          "value": 4500000
        },
        {
          "label": "Somalia",
          "value": 3100000
        },
        {
          "label": "Sudan",
          "value": 2500000
        },
        {
          "label": "South Sudan",
          "value": 4200000
        }
      ]
    },
    {
      "year": 2024,
      "rows": [
        {
          "label": "Sudan",
          "value": 14900000
        },
        {
          "label": "Syria",
          "value": 13800000
        },
        {
          "label": "Afghanistan",
          "value": 10300000
        },
        {
          "label": "Ukraine",
          "value": 9700000
        },
        {
          "label": "Colombia",
          "value": 6800000
        },
        {
          "label": "DR Congo",
          "value": 6400000
        },
        {
          "label": "Somalia",
          "value": 3700000
        }
      ]
    }
  ]
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
value_col = mapping.get("value_col") or next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])), df.columns[-1])
label_col = mapping.get("label_col") or next((c for c in df.columns if c not in (value_col, mapping.get("year_col"))), df.columns[0])
year_col = mapping.get("year_col") or next((c for c in df.columns if str(c).lower() in ("year", "yr", "date")), None)
if year_col is None:
    # pick a numeric column whose range looks like calendar years
    for c in df.columns:
        if c in (value_col, label_col):
            continue
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(v) and v.min() >= 1900 and v.max() <= 2100:
            year_col = c
            break
top_n = int(scene.get("top_n", mapping.get("top_n", 10)))
# optional per-label colour map (e.g. region bucket → hex), e.g. mapping["color_col"]
color_col = mapping.get("color_col")
work = df[[year_col, label_col, value_col] + ([color_col] if color_col else [])].copy()
work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
work = work.dropna(subset=[year_col, label_col, value_col])
frames = []
for yr, grp in work.groupby(year_col, sort=True):
    rows = []
    for _, r in grp.iterrows():
        row = {"label": str(r[label_col]), "value": float(r[value_col])}
        if color_col and pd.notna(r[color_col]):
            row["color"] = str(r[color_col])
        rows.append(row)
    yv = int(yr) if float(yr).is_integer() else yr
    frames.append({"year": yv, "rows": rows})
return {"frames": frames, "top_n": top_n}
```

**Notes:** Faithful port of build_race.py, adapted to the scene-engine contract.

MOTION/RELIABILITY: the LATEST frame is painted first as the resting geometry (correct at t=0 for headless-Chrome rasterization and backgrounded tabs), then opacity-faded in via H.in. Bar-race is the contract's explicit "inherently animated" exception, so the replay loop (earliest→latest, ending on latest) recomputes bar widths per frame via a d3.timer — width/transform changes happen ONLY inside the loop, never as the reveal mechanism. RM (prefers-reduced-motion) short-circuits the loop, leaving the static final frame. The replay starts after a 900ms delay so a screenshot taken near t=0 captures the final-frame resting state, not frame 0.

CSS: used only contract classes — 'axis' (gridline ticks via axisTop with tickSize(-ih)), 'axis-title', 'clabel' (in-bar entity label, white on wide bars / ink when label sits outside), 'vlabel' (mono value to the right of each bar), 'annot' (one optional italic-serif finding from scene.annotations[0]). The large background year numeral has NO matching class in the scaffold, so it is styled inline (var(--serif), grey at 55% fill-opacity) — no <style> injected, only inline style on that one element. opacity is controlled via attr('opacity',...) on the .row groups (H.in owns element 'opacity' on the gBars/yearMark wrappers); partial transparency uses fill-opacity, per the contract.

HIGHLIGHT-BY-COLOUR: by default every bar is neutral (H.hue → P.grey); only the label equal to scene.highlight gets P.signal. If the python_shaper is given a mapping['color_col'] (e.g. a region-bucket hex like the reference's BUCKET_COLOR), per-row d.frames[*].rows[*].color overrides and colours bars by region — that reproduces the reference's editorial region palette. Leave color_col unset for the sober highlight-one-entity default.

Simplifications vs the reference: dropped the interactive play/pause/scrub/speed UI and the linear inter-year interpolation (the scene engine renders a static-or-autoplay figure, not a controllable widget); frames are discrete with a fixed hold. The leader caption + takeaway cards + legend from the reference live in scene narrative fields (lede/caption/annotations) rather than chart chrome. d.frames[*].rows is the full per-year field; the renderer does the top_n slice + per-frame re-rank itself, matching build_race.py's render().

python_shaper expects a long/tidy DataFrame (one row per year×entity) and reads mapping {year_col, label_col, value_col, color_col?, top_n?}. Falls back to sensible auto-detection (year = a numeric col in 1900–2100; value = first numeric; label = first remaining). For inline data, pass d directly on the scene.

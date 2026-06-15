# Recipe — heatmap_matrix

**Data shape** (`scene.data`):
d = {
  origins: [{iso:"AFG", name:"Afghanistan"}, ...],   // matrix ROWS, sorted strict→generous in the order you want them stacked top→bottom
  dests:   [{iso:"GRC", name:"Greece"}, ...],          // matrix COLUMNS, sorted strict→generous left→right
  cells:   [{o:"AFG", d:"GRC", trr:0.41}, ...],         // one per visible (origin,destination); trr = recognition rate 0..1. OMIT a cell to render it as a hatched (suppressed, n<cell_min) blank.
  cell_min: 300,                                        // volume floor used for suppression; shown in the inline note
  spread:  {name:"Venezuela", lo:0.06, hi:1.0, pts:94}  // OPTIONAL widest-spread row to emphasise; name must match an origins[].name. pts = integer percentage-point swing for the annotation. Overridden by scene.highlight if set.
}
scene.highlight (optional): an origin NAME (string or [string]) to box+annotate instead of d.spread.name.
Each cell's % is PRINTED inside; colour is a sequential cobalt scale (oat→signalDim→signal), secondary to the number.

**Minimal sample** (`scene.data`):
```json
{
  "cell_min": 300,
  "origins": [
    {
      "iso": "AFG",
      "name": "Afghanistan"
    },
    {
      "iso": "SYR",
      "name": "Syria"
    },
    {
      "iso": "VEN",
      "name": "Venezuela"
    },
    {
      "iso": "IRQ",
      "name": "Iraq"
    },
    {
      "iso": "SOM",
      "name": "Somalia"
    }
  ],
  "dests": [
    {
      "iso": "GRC",
      "name": "Greece"
    },
    {
      "iso": "FRA",
      "name": "France"
    },
    {
      "iso": "SWE",
      "name": "Sweden"
    },
    {
      "iso": "NLD",
      "name": "Netherlands"
    },
    {
      "iso": "DEU",
      "name": "Germany"
    }
  ],
  "cells": [
    {
      "o": "AFG",
      "d": "GRC",
      "trr": 0.41
    },
    {
      "o": "AFG",
      "d": "FRA",
      "trr": 0.58
    },
    {
      "o": "AFG",
      "d": "SWE",
      "trr": 0.4
    },
    {
      "o": "AFG",
      "d": "DEU",
      "trr": 0.96
    },
    {
      "o": "SYR",
      "d": "GRC",
      "trr": 0.91
    },
    {
      "o": "SYR",
      "d": "FRA",
      "trr": 0.97
    },
    {
      "o": "SYR",
      "d": "SWE",
      "trr": 0.69
    },
    {
      "o": "SYR",
      "d": "NLD",
      "trr": 0.93
    },
    {
      "o": "SYR",
      "d": "DEU",
      "trr": 0.99
    },
    {
      "o": "VEN",
      "d": "FRA",
      "trr": 0.06
    },
    {
      "o": "VEN",
      "d": "SWE",
      "trr": 0.21
    },
    {
      "o": "VEN",
      "d": "NLD",
      "trr": 0.55
    },
    {
      "o": "VEN",
      "d": "DEU",
      "trr": 1
    },
    {
      "o": "IRQ",
      "d": "GRC",
      "trr": 0.33
    },
    {
      "o": "IRQ",
      "d": "FRA",
      "trr": 0.52
    },
    {
      "o": "IRQ",
      "d": "SWE",
      "trr": 0.44
    },
    {
      "o": "IRQ",
      "d": "NLD",
      "trr": 0.61
    },
    {
      "o": "IRQ",
      "d": "DEU",
      "trr": 0.78
    },
    {
      "o": "SOM",
      "d": "GRC",
      "trr": 0.62
    },
    {
      "o": "SOM",
      "d": "FRA",
      "trr": 0.71
    },
    {
      "o": "SOM",
      "d": "SWE",
      "trr": 0.83
    },
    {
      "o": "SOM",
      "d": "DEU",
      "trr": 0.9
    }
  ],
  "spread": {
    "name": "Venezuela",
    "lo": 0.06,
    "hi": 1,
    "pts": 94
  }
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
r = mapping  # expects mapping carrying: origin_col, dest_col, value_col, iso cols, cell_min
o_col   = mapping.get("origin_col", "origin")
d_col   = mapping.get("dest_col", "destination")
v_col   = mapping.get("value_col", "recognition_rate")
o_iso   = mapping.get("origin_iso_col", o_col)
d_iso   = mapping.get("dest_iso_col", d_col)
cnt_col = mapping.get("count_col")           # optional decision-volume column for suppression
cell_min = int(mapping.get("cell_min", 300))

work = df[[o_col, d_col, v_col]].copy()
work[v_col] = pd.to_numeric(work[v_col], errors="coerce")
# rates may arrive as 0..100 — normalise to 0..1
if work[v_col].dropna().abs().max() and work[v_col].dropna().abs().max() > 1.5:
    work[v_col] = work[v_col] / 100.0
work["__oiso"] = df[o_iso].astype(str)
work["__diso"] = df[d_iso].astype(str)
if cnt_col and cnt_col in df.columns:
    work["__n"] = pd.to_numeric(df[cnt_col], errors="coerce")
else:
    work["__n"] = cell_min  # no volume info → keep all cells

# generosity = mean rate; order rows/cols strict→generous
o_order = (work.groupby([o_col, "__oiso"])[v_col].mean()
              .sort_values().reset_index())
d_order = (work.groupby([d_col, "__diso"])[v_col].mean()
              .sort_values().reset_index())
origins = [{"iso": str(r["__oiso"]), "name": str(r[o_col])} for _, r in o_order.iterrows()]
dests   = [{"iso": str(r["__diso"]), "name": str(r[d_col])} for _, r in d_order.iterrows()]

cells = []
for _, row in work.dropna(subset=[v_col]).iterrows():
    if row["__n"] is not None and row["__n"] < cell_min:
        continue  # suppressed → omitted → hatched by the renderer
    cells.append({"o": str(row["__oiso"]), "d": str(row["__diso"]),
                  "trr": round(float(row[v_col]), 3)})

# widest-spread origin row for the emphasis box
sp = None
gp = work.dropna(subset=[v_col]).groupby([o_col])[v_col]
if len(gp):
    spreads = (gp.max() - gp.min()).sort_values(ascending=False)
    nm = spreads.index[0]
    sub = work[work[o_col] == nm][v_col].dropna()
    sp = {"name": str(nm), "lo": round(float(sub.min()), 3),
          "hi": round(float(sub.max()), 3),
          "pts": int(round((float(sub.max()) - float(sub.min())) * 100))}

return {"cell_min": cell_min, "origins": origins, "dests": dests,
        "cells": cells, "spread": sp}
```

**Notes:** Faithful port of build_heatmap.py with the contract's two mandated changes: (1) sequential COBALT scale (P.oat → P.signalDim → P.signal) instead of the reference's diverging clay→oat→olive, per the archetype spec; (2) only existing CSS classes used (clabel for axis labels, vlabel for the in-cell mono %, annot for the italic-serif spread annotation, axis/axis-title for the legend). No <style> injected.

MOTION: every element's final geometry is set at t=0; H.in animates opacity only. The cell-group fade uses staggered delay but the rects/text already carry full width/height/x/y, so a headless-Chrome screenshot at t=0 shows the complete matrix. Reduced-motion safe (H.in early-returns).

COLOUR & TEXT CONTRAST: in-cell % uses paper text when trr>0.45 (deep cobalt fill) else ink text. The number is primary, colour secondary, exactly as the reference intends.

SUPPRESSED CELLS: any (origin,destination) pair NOT present in d.cells renders as an SVG hatch pattern (url(#hm-hatch)) — the renderer-side equivalent of the reference's blank/suppressed treatment. The inline note "hatched = fewer than N decisions" mirrors the reference methodology aside. The python_shaper drops cells below cell_min so they become hatched.

HIGHLIGHT: scene.highlight (an origin name) wins; falls back to d.spread.name. The boxed row + "N-pt swing →" annotation reproduce the reference's widest-spread emphasis. If neither resolves to a known origin, no box is drawn (graceful).

SIZING: viewBox 1040x700 matches the reference; the engine's .figure svg is width:100% height:auto so it scales. dest/origin name shortening (the reference SHORT map) is NOT done here — pass already-shortened display names in origins[].name / dests[].name (the python_shaper passes them through verbatim).

DATA SHAPE: minimal & JSON-serializable — origins/dests are {iso,name} lists fixing row/column order (sort them strict→generous before passing); cells are flat {o,d,trr} records keyed by iso. spread is optional. python_shaper builds all of this from a long DataFrame given a mapping with origin/dest/value (+optional iso + count columns); it auto-normalises 0..100 rates to 0..1 and computes the widest-spread row.

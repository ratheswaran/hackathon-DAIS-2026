# Recipe — sankey_corridors

**Data shape** (`scene.data`):
d = {
  nodes: [ {name: string, other?: bool, side?: 'orig'|'host'} , ... ],
  links: [ {source: int, target: int, value: number} , ... ]
}

- `source`/`target` are 0-based INDEXES into `nodes` (the d3-sankey default nodeId). NOT names.
- A country that is both an origin and a host MUST appear as TWO separate node entries (one on each side) so the flow reads strictly left→right; the Python shaper does this automatically by emitting per-side nodes.
- `other:true` on a node marks the bundled "all other corridors" pseudo-node pair (faint grey, never labelled as the headline, excluded from accent colouring). Optional but recommended so the chart shows the long tail.
- `side` is optional: if omitted the renderer infers origin (left) vs host (right) from the computed sankey x-position. The shaper sets it explicitly.
- value = refugee count for that origin→host corridor (raw number; H.fmt renders it K/M/B).

scene fields consumed: scene.title (svg aria-label), scene.highlight (origin NAME string or array of names → those origins' outgoing links accent P.signal, everything else P.grey; if null, the single biggest origin gets P.signal and the rest grey).

**Minimal sample** (`scene.data`):
```json
{
  "nodes": [
    {
      "name": "Afghanistan"
    },
    {
      "name": "Syria"
    },
    {
      "name": "Ukraine"
    },
    {
      "name": "Venezuela"
    },
    {
      "name": "South Sudan"
    },
    {
      "name": "Iran"
    },
    {
      "name": "Pakistan"
    },
    {
      "name": "Germany"
    },
    {
      "name": "Turkey"
    },
    {
      "name": "Colombia"
    },
    {
      "name": "Uganda"
    },
    {
      "name": "Poland"
    },
    {
      "name": "all other corridors",
      "other": true
    },
    {
      "name": "(≈ 4,690 routes)",
      "other": true
    }
  ],
  "links": [
    {
      "source": 0,
      "target": 5,
      "value": 3800000
    },
    {
      "source": 0,
      "target": 6,
      "value": 2180000
    },
    {
      "source": 1,
      "target": 8,
      "value": 3160000
    },
    {
      "source": 1,
      "target": 7,
      "value": 716000
    },
    {
      "source": 2,
      "target": 7,
      "value": 1180000
    },
    {
      "source": 2,
      "target": 11,
      "value": 957000
    },
    {
      "source": 3,
      "target": 9,
      "value": 1840000
    },
    {
      "source": 4,
      "target": 10,
      "value": 920000
    },
    {
      "source": 12,
      "target": 13,
      "value": 13200000
    }
  ]
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
value_col = mapping.get("value_col") or "value"
orig_col  = mapping.get("origin_col") or mapping.get("source_col") or "origin"
host_col  = mapping.get("host_col") or mapping.get("target_col") or "host"
top_n     = int(scene.get("top_n", mapping.get("top_n", 22)))

w = df[[orig_col, host_col, value_col]].copy()
w[value_col] = pd.to_numeric(w[value_col], errors="coerce")
w = w.dropna(subset=[orig_col, host_col, value_col])
w = w[w[value_col] > 0]
# cross-border only: drop self-loops (origin == host)
w = w[w[orig_col].astype(str).str.strip() != w[host_col].astype(str).str.strip()]

g = (w.groupby([orig_col, host_col], as_index=False)[value_col].sum()
       .sort_values(value_col, ascending=False)
       .reset_index(drop=True))
total = float(g[value_col].sum())
n_corr = int(len(g))

top = g.head(top_n)
other_val = total - float(top[value_col].sum())

# per-side nodes so a country that is both origin and host splits left/right
nodes, idx = [], {}
def node(name, side, other=False):
    key = (side, name)
    if key in idx:
        return idx[key]
    i = len(nodes)
    idx[key] = i
    nodes.append({"name": str(name), "side": side, **({"other": True} if other else {})})
    return i

links = []
for _, r in top.iterrows():
    s = node(r[orig_col], "orig")
    t = node(r[host_col], "host")
    links.append({"source": s, "target": t, "value": int(round(float(r[value_col])))})

# bundle the long tail into one faint origin→host band (omit if nothing left)
n_drawn = int(len(top))
if other_val > 0 and n_corr > n_drawn:
    s = node("all other corridors", "orig", other=True)
    t = node(f"(≈ {n_corr - n_drawn:,} routes)", "host", other=True)
    links.append({"source": s, "target": t, "value": int(round(other_val))})

return {"nodes": nodes, "links": links}
```

**Notes:** PORT FIDELITY: faithful to build_corridors.py — per-side nodes (orig/host split for dual-role countries), origin labels left of the rect + value below, host labels right, a faint grey bundled "all other corridors" band, column headers, a finding annotation for the biggest single corridor, and a largest-first opacity-only reveal stagger. Adapted to the engine: the reference's clay/region palette is replaced by the RA cobalt palette + highlight-by-colour (links coloured by SOURCE node; the single biggest origin = P.signal by default, everything else P.grey; scene.highlight names which origin(s) get accented). Headers/labels use the allow-list classes (axis-title / clabel / vlabel / annot) instead of the reference's bespoke colhead/nodelabel/nodeval classes.

MOTION SAFETY: final link path "d" + stroke-width and node rect width/height are set immediately; the only animation is H.in (opacity). Verified with jsdom that every path has a valid "d" and stroke-width≥1 and every rect has positive geometry at t=0, so headless-Chrome rasterization and backgrounded tabs show the correct Sankey. Partial transparency uses the stroke-opacity / fill-opacity ATTRS (not style.opacity), so H.in's element-opacity animation does not clobber them. Under reduced-motion H.in is a no-op and geometry stays put.

EXTRA CDN: requires d3-sankey (one tag in extra_cdn). d3-sankey 0.12.3 attaches d3.sankey / d3.sankeyLinkHorizontal onto the global d3 when the UMD bundle loads after d3 core — matches the engine's existing <script> include pattern.

REGISTER: add "sankey_corridors" to the Python `_ARCHETYPES` set and to the tool's `scenes` type-enum docstring so the orchestrator can route to it.

DATA SHAPE GOTCHA: links use INTEGER indices into nodes (d3-sankey default nodeId), not names. The python_shaper emits this directly. If an agent hand-authors inline `data`, it must index, and must split a dual-role country into two node entries (one orig, one host).

LAYOUT: viewBox 720x520 (taller than the engine's other wide charts because Sankey stacks rows vertically; nodePadding 9 / nodeWidth 13 / 150px label gutters each side match the reference). The node-label threshold (6% of the max node value) suppresses clutter on thin tail rows — increase it if a dense deck still overlaps. The python_shaper defaults to top_n=22 drawn corridors (reference default); set scene.top_n lower for a tighter chart.

VOICE: sober, no emoji. Tooltips and the annotation say "refugees"; keep the IDP/asylum-seeker distinction upstream (the shaper does no category mixing — pass it a refugees-only corridor frame).

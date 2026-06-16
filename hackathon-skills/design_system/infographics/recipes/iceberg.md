# Recipe — iceberg

**Data shape** (`scene.data`):
d = {
  above: { label: string, value: number },   // the visible / above-waterline segment (e.g. "Districts with at least one facility")
  below: { label: string, value: number }     // the hidden / below-waterline mass (e.g. "Districts with zero facilities")
}
Values are raw counts in the SAME unit (districts, facilities, or millions — the renderer only uses ratios value/(above+below) for the bar split + the % labels, so absolute scale is arbitrary as long as both share it). The bar is always 100% wide: above starts at x=0, below stacks immediately after. Percent labels and the "X% have no facility in the sample" annotation are computed from the share. scene.highlight (optional) = the label of the segment to accent in signal-cobalt (matched against above.label / below.label); if omitted, above renders signal and below renders neutral grey. scene.value_label (optional) = a small uppercase footer unit string.

**Minimal sample** (`scene.data`):
```json
{
  "title": "The coverage iceberg, NFHS-5 districts",
  "kicker": "Virtue Foundation · Healthcare access",
  "lede": "The facilities we can count describe only the visible tip of need.",
  "scenes": [
    {
      "type": "iceberg",
      "eyebrow": "The reframe",
      "title": "Counted facilities describe only the tip",
      "lede": "Districts with at least one facility in the sample are barely a third; the largest group has none recorded at all.",
      "caption": "Above the waterline: districts with at least one sampled facility. Below: districts with zero facilities in the sample (coverage gap, not necessarily true supply).",
      "value_label": "share of all NFHS-5 districts",
      "data": {
        "above": {
          "label": "Districts with at least one facility",
          "value": 453
        },
        "below": {
          "label": "Districts with zero facilities (sample)",
          "value": 245
        }
      }
    }
  ],
  "methodology": "NFHS-5 district frame. Facilities is a ~10k SAMPLE (coverage, not a census); a zero count means no sampled facility, not a verified absence of all care. Joined via the India Post PIN→district crosswalk.",
  "source": "Source: Virtue Foundation healthcare-access dataset; NFHS-5 district health indicators; India Post PIN directory."
}
```

**How to compute it** (run this in `run_python_code` over the stored DataFrame(s), then pass the result as the scene's inline `data`):
```python
# df = the stored DataFrame; mapping = your column mapping; scene = the scene dict
if scene.get("data") is not None:
    return scene["data"]
mp = scene.get("mapping", {}) or {}
# Two natural shapes:
#  (A) wide row: one row with an `above` numeric col + a `below` numeric col.
#  (B) long table: a category col + a value col, where `above_categories`
#      (list) names which categories sum into the above-waterline tip and the
#      rest fall below. mapping = {label_col, value_col, above_categories,
#      above_label?, below_label?}.
cat = mp.get("label_col")
val = mp.get("value_col")
above_col = mp.get("above_col")
below_col = mp.get("below_col")
if above_col and below_col:  # shape A
    av = float(pd.to_numeric(df[above_col], errors="coerce").dropna().sum())
    bv = float(pd.to_numeric(df[below_col], errors="coerce").dropna().sum())
    return {
        "above": {"label": mp.get("above_label", above_col), "value": av},
        "below": {"label": mp.get("below_label", below_col), "value": bv},
    }
if cat and val:  # shape B
    above_cats = set(str(c) for c in (mp.get("above_categories") or []))
    sub = df[[cat, val]].dropna().copy()
    sub[val] = pd.to_numeric(sub[val], errors="coerce")
    sub = sub.dropna()
    av = float(sub[sub[cat].astype(str).isin(above_cats)][val].sum())
    bv = float(sub[~sub[cat].astype(str).isin(above_cats)][val].sum())
    return {
        "above": {"label": mp.get("above_label", "Above waterline"), "value": av},
        "below": {"label": mp.get("below_label", "Below waterline"), "value": bv},
    }
return {}
```

**Notes:** Ported from renderIceberg in the flagship builder, simplified to the brief's 2-segment {above, below} shape (the reference used a 4-segment stacked bar with the waterline at the visible-vs-hidden boundary; the {above,below} contract collapses that to visible-tip vs hidden-mass, which is the same reframe and the same waterline position). Visual idea preserved: single 100%-width horizontal bar, white % labels inside each segment, dashed waterline rule on the boundary, the "X% have no facility in the sample" serif annotation under the below-mass, and the "covered — X% →" tip annotation above the line.

MOTION: fully reduced-motion / screenshot safe. Every rect has its FINAL width set at t=0; the dashed waterline has its dash array set immediately (NO stroke-dashoffset reveal, unlike the reference which animated the line drawing on); all motion is opacity-only via H.in. Rects use solid fill (no fill-opacity attr), so H.in's style('opacity') animation is the only opacity channel and nothing is clobbered.

HIGHLIGHT: default (no scene.highlight) renders the above-waterline tip in signal cobalt and the below mass in neutral grey, with the below annotation also in signal to point at the hidden bulk — this mirrors the reference's clay-tip/blue-mass contrast intent within the RA palette. If scene.highlight is set, it matches against above.label / below.label and only the named segment gets the signal accent (everything else grey); the below annotation then drops to slate.

Uses only existing CSS classes (vlabel, annot, axis-title) and only P palette colours + '#fff' for in-bar labels (matches the reference's white-on-bar value labels and the other renderers' .attr('fill','#fff') pattern). No <style> injected, no extra CDN. viewBox 720x420 (wide chart) consistent with line_multi/stacked_area.

The renderer reads share = value/(above+below), so the two values may be passed as raw persons OR as millions OR as any consistent unit; only the ratio matters for the bar split and the % labels. python_shaper supports both a wide row (above_col + below_col) and a long category table (label_col + value_col + above_categories list) → null was not returned because there IS a natural DataFrame->shape here.

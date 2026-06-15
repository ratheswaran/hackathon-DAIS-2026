# Chart Selection Matrix

This skill supports only seven chart types. Select from this set, or reject all seven if the data relationship is unsupported.

## Primary mapping

| Data relationship | Recommended chart | Use when | Avoid when |
| --- | --- | --- | --- |
| Compare discrete categories or simple time buckets | Bar | Users need to compare lengths, ranking, or category differences | The main message is continuous change over time |
| Show change over time or another ordered continuous sequence | Line | The sequence is ordered and trend direction matters | Categories are unordered or there are too many lines |
| Show magnitude over time, often with cumulative emphasis | Area | The change over time matters and filled volume helps the story | Precise comparison between overlapping series matters most |
| Show part-to-whole at one moment | Pie | There are only a few slices and the message is composition | There are many slices, close values, or any trend over time |
| Show part-to-whole with a meaningful total/label in the center | Donut | Pie logic applies and the center adds useful context | The center is decorative only |
| Show three quantitative variables | Bubble | X, Y, and bubble size are all numeric and comparative | One dimension is categorical or size must be read precisely |
| Compare profiles against shared bounded criteria | Radar | All axes share the same scale and the message is profile shape | Exact value reading is the priority |

## Quick decision rules

- Choose `Bar` for ranking, side-by-side category comparison, or simple bucketed time comparison.
- Choose `Line` for continuous or ordered sequences where direction and rate of change matter.
- Choose `Area` when line would fit, but showing filled magnitude or stacked contribution over time improves the story.
- Choose `Pie` or `Donut` only for simple composition at a single point in time.
- Choose `Bubble` only when three quantitative dimensions must be visible in one view.
- Choose `Radar` only when the audience needs a profile comparison across repeated criteria.

## Reject conditions

Reject all seven if the request fundamentally needs:
- Distribution analysis
- Dense correlation analysis across many points or categories
- Exact table-like readout
- Complex hierarchy
- Flow or process relationships
- Geospatial data

In those cases, explain that the supported set does not cover the needed relationship.

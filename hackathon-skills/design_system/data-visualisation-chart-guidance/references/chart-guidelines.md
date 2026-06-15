# Chart Guidelines

Use this document after the chart-selection matrix identifies the closest chart type.

## Bar chart

### When to use
- Compare discrete categories.
- Show ranking from highest to lowest or lowest to highest.
- Compare simple time buckets when continuity between points is not the message.

### When not to use
- The primary message is continuous change over time.
- There are too many categories for readable labels.
- The bars would become too thin to compare confidently.

### Required data shape
- One quantitative measure per category, or a small number of grouped/stacked measures.
- Categorical labels on one axis.
- A zero baseline for bar length comparison.

### Visual structure rules
- Use vertical bars for shorter labels and common ranking views.
- Use horizontal bars for long category names.
- Start the quantitative axis at zero.
- Use grouped bars only when side-by-side comparison is the main task.
- Use stacked bars only when composition within each category matters and exact segment comparison is secondary.

### Label and legend rules
- Sort intentionally, usually by value or natural category order.
- Show direct labels when there are few bars; use an axis when there are many.
- Use a legend only when multiple series cannot be directly labeled.

### Colour rules
- Single-series default: `--signal` = `#254BB2` (cobalt).
- For highlighted comparison, pair `--signal #254BB2` with the `--grey #C7C2B6` neutral track/background (see data-vis-colour-rules → highlight-by-colour).
- For multi-category bars, use the categorical sequence in strict order (`--signal` → `--amber` → `--cyan` → `--magenta` → `--slate` → `--mute`), then `Others` = `--grey`.

### Anti-patterns
- Do not truncate the value axis away from zero.
- Do not use too many categories in one view.
- Do not use stacked bars when users need exact comparison across segments.
- Do not use bar charts to imply continuity better shown by line.

## Line chart

### When to use
- Show trends across time or another ordered sequence.
- Compare a small number of series over the same ordered scale.
- Emphasize direction, turning points, and rate of change.

### When not to use
- Categories are unordered.
- There are too many lines to track comfortably.
- Filled magnitude is more important than the line itself.

### Required data shape
- An ordered x-axis.
- One or more quantitative series measured on a shared scale.
- Consistent intervals whenever the sequence implies time.

### Visual structure rules
- Keep the x-axis ordered and evenly interpreted.
- Use markers when the data is sparse or point-by-point reading matters.
- Omit or downplay markers when the series is dense and the line is the message.
- Limit series count so users can still follow each line.

### Label and legend rules
- Direct-label line endings when possible.
- Use a legend only when direct labels would clutter the plot.
- Keep axis labels sparse but sufficient to preserve sequence clarity.

### Colour rules
- Single-series default: `--signal` / `#254BB2` (cobalt).
- For multi-series lines, apply the categorical sequence in strict order.
- Avoid heavy fills; line colour should carry the primary distinction.

### Anti-patterns
- Do not use line for unordered categories.
- Do not overload the chart with many series.
- Do not use thick fills or styling that turns the chart into an area chart unintentionally.
- Do not connect values across inconsistent or misleading intervals.

## Area chart

### When to use
- Show change over time with emphasis on magnitude.
- Show cumulative contribution over time.
- Use stacked area when composition over time matters more than exact series comparison.

### When not to use
- Users need precise comparison between multiple overlapping series.
- The filled area obscures the main insight.
- The sequence is unordered.

### Required data shape
- An ordered x-axis.
- One quantitative series, or a small number of stacked series.
- Stable intervals if the sequence is time-based.

### Visual structure rules
- Keep the top edge legible; the line boundary should remain clear.
- Use subtle fill so the chart still reads as data, not decoration.
- Prefer single-series area or stacked area over multiple overlapping filled series.
- Keep stacking order intentional and stable across the sequence.

### Label and legend rules
- Direct-label the top line or stack groups when space allows.
- Use a legend for stacked series only when direct labeling is impractical.
- Keep axis labels readable; the fill should not replace numeric context.

### Colour rules
- Single-series default: `--signal` / `#254BB2` (cobalt) with a lighter fill treatment of the same series colour.
- For stacked series, use the categorical sequence in strict order.
- Use ordered or level palettes only if the stacked areas represent ordered meaning rather than arbitrary categories.

### Anti-patterns
- Do not use overlapping filled multi-series area charts for exact comparison.
- Do not use area if a line chart would communicate the trend more cleanly.
- Do not make the fill so opaque that gridlines, labels, or other series disappear.

## Pie chart

### When to use
- Show simple part-to-whole composition at one point in time.
- Show a small number of slices with clearly different proportions.

### When not to use
- There are more than a few slices.
- Values are close and users need precise comparison.
- The story is a trend over time.
- Data includes negatives or does not form one meaningful whole.

### Required data shape
- One total divided into categories.
- One moment or one aggregate state.
- Positive values only.

### Visual structure rules
- Prefer 2-5 slices.
- Order slices consistently, ideally largest to smallest.
- Keep slice count low enough that each segment stays readable.
- Keep the overall circle clean and not overloaded with labels.

### Label and legend rules
- Prefer direct labeling when there are few slices.
- Use a legend only if direct labels are not practical.
- Keep labels short and focused on category plus value or percentage.

### Colour rules
- Use the categorical sequence in strict order from `--signal` onward.
- For 6+ categories, aggregate the remainder as `Others` = `--grey` `#C7C2B6`.
- Keep slices on a light surface for v1.

### Anti-patterns
- Do not use pie for many categories.
- Do not use pie for close-value comparison that needs precision.
- Do not use pie to show change over time.
- Do not mix arbitrary colour order; keep the sequence stable.

## Donut chart

### When to use
- Use for the same part-to-whole cases as pie.
- Prefer it when the center can hold a useful total, label, or summary.

### When not to use
- The center has no real informational value.
- Slice count is too high.
- Precise slice comparison is important.

### Required data shape
- One total divided into categories.
- Positive values only.
- One moment or one aggregate state.

### Visual structure rules
- Keep ring thickness consistent.
- Use the center only for a meaningful total, label, or title.
- Preserve enough slice width for small categories to remain visible.
- Keep the composition simple enough to read around the ring.

### Label and legend rules
- Keep center text hierarchy clear: summary first, secondary detail second.
- Prefer direct slice labels when feasible; otherwise use a legend.
- Keep label count manageable.

### Colour rules
- Use the categorical sequence in strict order.
- Use `Others` = `--grey #C7C2B6` only when an aggregated remainder is necessary.
- Keep the center area neutral so the data ring remains dominant.

### Anti-patterns
- Do not choose donut only for style if pie communicates better.
- Do not overcrowd the ring with too many tiny slices.
- Do not place decorative or redundant copy in the center.

## Bubble chart

### When to use
- Show three quantitative dimensions in one view.
- Compare relative position on x and y while also showing scale through bubble area.
- Highlight notable outliers or clusters when the point count remains manageable.

### When not to use
- One or more dimensions are categorical instead of numeric.
- There are so many bubbles that overlap destroys readability.
- Users need exact reading of the size dimension.

### Required data shape
- Numeric x values.
- Numeric y values.
- Numeric size values encoded by bubble area, not diameter.

### Visual structure rules
- Keep overlap manageable.
- Use a size range wide enough to distinguish bubbles but not so wide that one bubble dominates the plot.
- Label only key bubbles or outliers.
- Preserve visible axes and grid context for position reading.

### Label and legend rules
- If size needs explanation, provide a bubble-size legend or a concise note.
- Direct-label only the most important points.
- Keep axis labels explicit because the plot carries multiple dimensions.

### Colour rules
- Single-series default: `--signal` / `#254BB2` (cobalt).
- Use multiple colours only when colour encodes a separate categorical grouping and the point count stays readable.
- If multiple colours are used, follow the categorical sequence in strict order.

### Anti-patterns
- Do not encode size by diameter.
- Do not use bubble charts for exact size comparison claims.
- Do not create dense point clouds that users cannot parse.
- Do not introduce colour as a fourth variable unless it genuinely helps.

## Radar chart

### When to use
- Compare one or a few profiles across the same bounded criteria.
- Show strengths and weaknesses across repeated dimensions.
- Emphasize overall shape rather than exact numeric precision.

### When not to use
- Users need exact value comparison.
- There are too many axes or too many series.
- The criteria do not share a consistent scale or meaning.

### Required data shape
- A shared set of criteria.
- One common scale across every axis.
- Bounded values that make the radial frame meaningful.

### Visual structure rules
- Keep the number of axes small enough to read comfortably.
- Keep series count low.
- Use subtle fill and a clear outline.
- Preserve the radial grid so users can estimate the profile shape.

### Label and legend rules
- Keep axis labels short.
- Use a legend only when more than one series is shown and direct labeling is not possible.
- State the shared scale if it is not obvious from context.

### Colour rules
- Single-series default: `--signal` / `#254BB2` (cobalt).
- For multi-series radar charts, use the categorical sequence in strict order.
- Keep fills subtle and outlines visible.

### Anti-patterns
- Do not use radar for precise comparisons.
- Do not overload the chart with many axes or many series.
- Do not compare criteria that are not truly parallel or do not share a scale.

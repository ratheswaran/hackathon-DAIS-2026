---
name: data-visualisation-chart-guidance
description: Select the right chart type and define how it should be designed. Use when an agent needs to choose between bar, line, area, pie, donut, bubble, and radar charts; validate whether a proposed chart is appropriate; explain why one chart is a better fit than nearby alternatives; or produce an editorial chart specification using approved data-visualisation tokens, colour order, and chart-specific design rules.
---

# Data Visualisation Chart Guidance

Use this skill for chart recommendation and chart-spec writing in the editorial design system.

> **Note:** the chart-choice theory below (Cleveland–McGill ranking, the
> seven-chart selection matrix) is domain-agnostic and still applies. The
> legacy Plotly `render_chart` tool it once described no longer exists on this
> fork — rich charts are composed via `compose_infographic` / `compose_story`
> (see [`../SKILL.md`](../SKILL.md)). Read the theory here, render there.

This skill is intentionally limited to these seven chart types only:
- Bar
- Line
- Area
- Pie
- Donut
- Bubble
- Radar

Do not recommend any chart outside this list.
If none of the seven fits the request, say so explicitly and explain why.

## Operating Principle

Prioritise communication accuracy over visual novelty.
Choose the chart that makes the intended message easiest to read and hardest to misinterpret.
Do not force a familiar chart type when the data relationship does not support it.

## Response Contract

Structure the response in this order:

1. State the data relationship being shown.
2. Recommend one chart type from the allowed seven, or explicitly reject all seven.
3. Explain why the recommendation fits.
4. Explain why the nearest alternative chart types are weaker.
5. Provide a visual spec for the chosen chart.
6. Provide approved colour tokens and hex values.
7. List warnings and anti-patterns for the chosen chart.

If none of the seven chart types fit, answer with:
- No supported chart is appropriate.
- Why none of the seven fits.
- What data relationship is missing from the supported set.

## Selection Checks

Before choosing a chart, confirm:
- Is the message comparison, trend, composition, correlation, or profile?
- Is the x-axis ordered or unordered?
- How many categories or series are present?
- Does the audience need precise comparison or only pattern recognition?
- Does the chart need ranking, direct labels, or a center total?

Use the chart-selection matrix in `references/chart-selection-matrix.md`.
Use the detailed chart rules in `references/chart-guidelines.md`.
Use the colour and token rules in `references/data-vis-colour-rules.md`.

## Required Behaviour

- Stay light-theme only for v1.
- Use only the documented data-visualisation tokens and hex values from the bundled references.
- Keep recommendations within the supported seven-chart set.
- Use semantic colours only when the chart is explicitly encoding status semantics.
- Keep visual specifications concrete: axes, labels, legends, fills, ordering, and colour assignment.
- Reject misleading chart choices instead of softening the answer.

## What A Good Answer Does

A strong answer:
- Names the actual data relationship before naming the chart.
- Chooses the chart for readability and interpretability.
- Explains why nearby alternatives are weaker in this case.
- Gives enough design detail for another designer or agent to produce the chart consistently.
- References exact editorial data-visualisation tokens and documented hex values when colour choice matters.

A weak answer:
- Names a chart without explaining the relationship.
- Uses pie or donut for too many slices.
- Uses line for unordered categories.
- Uses area when the task needs precise multi-series comparison.
- Uses bubble when x, y, and size are not all quantitative.
- Uses radar for exact reading tasks.

## Output Format

Use this structure unless the user asks for a different one:

```markdown
Data relationship
- <comparison/trend/composition/correlation/profile>

Recommended chart
- <one of the seven supported chart types, or "no supported chart">

Why it fits
- <2-4 short points>

Why not the nearest alternative
- <1-3 short points on the most likely incorrect alternative>

Visual spec
- <layout, axis treatment, labels, legend, ordering, line/fill/bar treatment>

Colour and tokens
- <token name + hex + where it applies>

Warnings
- <anti-patterns to avoid>
```

## Chart-Specific Detail

For the selected chart, always pull the detailed rules from `references/chart-guidelines.md`, including:
- When to use
- When not to use
- Required data shape
- Visual structure rules
- Label and legend rules
- Colour rules
- Anti-patterns

Do not answer with only generic advice when the chart-specific reference provides a clearer rule.

## Data Shape — Long-Format vs Wide-Format

When composing a multi-series chart, mind the DataFrame shape — the same
distinction applies regardless of rendering tool:

**Wide format** — one column per series (e.g. one indicator column per year):
each value column becomes its own series/trace.

**Long format** — one row per (category, x) pair: a single categorical column
distinguishes the series, so you must declare which column carries the series
identity. Rendering a line/bar/area on long-format data *without* naming that
series column collapses every row into one trace, so the line zigzags through
points in row order.

If the series column isn't obvious (mixed long/wide, more than one candidate
categorical column), pivot to wide format first (one column per series) before
charting.

# India Healthcare Access — Genie space config

Curated `serialized_space` for the orchestrator's primary data-retrieval Genie
space (`ask_genie_space` → space `01f168ec4bf01d27a00ac8069c1b06b8`, over the
three Virtue Foundation tables on warehouse `7a84995ca3aefed0`).

| File | What |
|------|------|
| `india_healthcare_access.serialized.json` | The full v2 `serialized_space`: 1 instruction block + 9 certified Q→SQL exemplars + 6 sample questions. Source of truth. |
| `apply.py` | Idempotent push to the live space (sorts id-arrays, fetches etag, `update_space`). `--verify` runs every exemplar on the warehouse. |

## Why this exists
A bare Genie space (tables only) blind-scans the messy tables — slow + it fails
on the string-numeric / `'*'`-suppressed columns. The instructions + certified
SQL turn it into a fast, correct surface. The instruction content is distilled
from the Aura find_skill graph's Rules + Columns + SqlPatterns.

## Re-apply (e.g. after recreating the space)
```bash
cd hackathon-orchestrator-neo4j/prep/genie_space
PROFILE=hackathon python apply.py --verify   # expect: 9 OK / 0 FAIL
```

## Two format gotchas (both baked correctly into the JSON — don't regress on hand-edit)
1. Every id-bearing array must be **sorted by `id`** or the API rejects it.
2. PIN extraction uses `try_cast(regexp_extract(...,'([0-9]{6})',1) AS INT)` —
   plain `CAST('' AS INT)` hard-fails the whole Genie message. And never filter
   `col <> '*'` on the DOUBLE NFHS headline columns; cast in a subquery + filter
   `IS NOT NULL`.

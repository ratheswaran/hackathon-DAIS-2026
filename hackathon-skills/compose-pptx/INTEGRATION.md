# Wiring `compose_deck` into the hackathon orchestrator

`compose_deck` is **additive** — it owns presentation decks (`.pptx` with
native charts + HTML preview). `compose_document` keeps **docx / xlsx /
csv / pdf**. Both upload to the same `documents/` volume folder.

Files added by this skill:

```
hackathon-orchestrator/tools/compose_deck.py        ← the tool (RA-branded renderer)
hackathon-skills/compose-pptx/                       ← this skill (symlinked as /skills/compose-pptx/)
  SKILL.md  spec_reference.md  design.md
  design_system_deck_example.html  tokens.css
  templates/README.md          ← where to drop ra_template.pptx
  assets/                       ← brand assets for building the template
```

Apply the five steps below, then deploy.

## 1. Dependency (already satisfied)

`requirements.txt` already ships `python-pptx` (used by
`compose_document`). For best native-chart fidelity, bump the pin:

```diff
- python-pptx>=0.6.21
+ python-pptx>=1.0.0
```

No other deps — the renderer draws the brand-mark and orb natively.

## 2. `deploy_orchestrator_agent.py`

**a. Import** (next to the other tool imports, ~line 1917):

```python
from tools.compose_deck import build_compose_deck_tool
```

**b. Allow-list** — add to the inline `ALLOWED_TOOLS` set (~line 512):

```python
    "compose_deck",
```

**c. Instantiate the factory** — right after the `_compose_document =
build_compose_document_tool(...)` block (~line 2491):

```python
_compose_deck = build_compose_deck_tool(
    workspace_client=_workspace_client,
    variable_store_cls=VariableStore,
    app_url=APP_URL,
)
```

**d. Add to the orchestrator's tool list** (~line 2524, alongside
`_compose_document`):

```python
    _compose_deck,        # Presentation decks → Volumes pptx + html (RA brand)
```

(Decks are an orchestrator-level deliverable. You can also add
`_compose_deck` to the `data_viz` sub-agent's tool list if you want the
viz sub-agent to build decks directly.)

**e. Skill scope** — the agent that calls `compose_deck` must be able to
`read_file("/skills/compose-pptx/...")`. The orchestrator already has the
skills root mounted; confirm its `skills=` includes `/skills/` (or add
`/skills/compose-pptx/`). If you wire it onto `data_viz` (scoped to
`/skills/design_system/`), add `/skills/compose-pptx/` to that sub-agent's
`skills=` list too.

## 3. `subagents/prompts.py`

The current rule (~line 452) routes **everything** office-format to
`compose_document`. Split decks out to `compose_deck`. Replace that bullet
with:

```
- **Presentation decks go through ``compose_deck``.** When the user asks
  for slides / a deck / a presentation / a PowerPoint, call
  ``compose_deck(title=..., deck_spec=[...])`` (one JSON spec; see the
  compose-pptx skill). It renders an editable .pptx with NATIVE charts +
  an HTML preview and returns ``preview_url`` + ``pptx_url``. Surface both.
- **Other binary office docs go through ``compose_document``** (docx /
  xlsx / csv / pdf), never ``run_python_code``. [keep the rest of the
  existing rationale — UC tmpfs trap, trace tr-83d05…]
```

And in the keyword-routing list (~line 601), point "deck / slides /
powerpoint / presentation" at `compose_deck`, leaving "word doc / excel /
spreadsheet / csv / pdf" on `compose_document`.

## 4. Node app — `/api/decks/:id` route

`compose_deck` returns `…/api/decks/<id>` (preview) and
`…/api/decks/<id>.pptx`. Add a route mirroring `documents.ts`. It lists
the shared documents folder and matches the file whose name starts with
`<id>__`:

```ts
// server/src/routes/decks.ts
import { Router } from "express";
const r = Router();
const FOLDER = "/Volumes/workspace/ai_ops/agent_scratch/documents";

async function pick(id: string, ext: "html" | "pptx") {
  // list FOLDER via /api/2.0/fs/directories, find name starting `${id}__` ending `.${ext}`
  // then fetch via /api/2.0/fs/files  (same client as documents.ts)
}

r.get("/api/decks/:id.pptx", async (req, res) => {
  const buf = await pick(req.params.id, "pptx");
  res.setHeader("Content-Type",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation");
  res.setHeader("Content-Disposition", `attachment; filename="${req.params.id}.pptx"`);
  res.send(buf);
});

r.get("/api/decks/:id", async (req, res) => {           // HTML preview (inline)
  const buf = await pick(req.params.id, "html");
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.send(buf);
});
export default r;
```

Register it in `index.ts` next to the documents route. (If you'd rather
not add a route, the deck `.pptx`/`.html`/`.json` already land in the
`documents/` folder — but the existing `/api/documents/:id` proxy picks
*one* file per id and won't distinguish preview-vs-pptx, so the dedicated
`/api/decks` route is recommended.)

## 5. Deploy + free-edition smoke test

After wiring, deploy as usual and ask the agent for a deck ("make me a
3-slide deck on X"). Expect a `compose_deck` call returning two URLs.
Verify the `.pptx` opens with editable charts and the preview renders the
cobalt-orb cover. The tool logs `[compose_deck] template mode ON` only
when `ra_template.pptx` is present (see `templates/README.md`).

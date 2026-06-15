# Hackathon demo script — the knowledge-graph data agent

App: `https://pudding-chatbot-7474656877852004.aws.databricksapps.com`
Endpoint: `agents_workspace-hackathon-orchestrator_agent_neo4j` (gpt-5.5, scale-to-zero)

**One-line pitch:** *"We replaced the agent's skills folder with a Neo4j knowledge
graph — it doesn't read files to figure out what to do, it traverses a graph. Same
data, −58% tokens, and every answer comes with a map of how the agent thought."*

**Pre-demo checklist (10 min before):**
- [ ] Warm the endpoint: send "hello" in a throwaway chat (scale-to-zero cold start ≈ 2–4 min).
- [ ] Open the **Knowledge graph** header button once — confirm the 738-node explorer loads.
- [ ] Have this script + a fallback browser tab with previously generated artifacts open.

---

## Beat 0 — Frame it (30s, no typing)

Say: *"Every data team writes runbooks — which data source answers what, the SQL
that's right, the gotchas. Agents usually consume that as files they grep and
re-read, every single turn. We disassembled ours into a 738-node knowledge graph:
domains, Genie spaces, tables, metrics, rules, SQL patterns, chart recipes,
findings — 1,700 typed relationships. One tool, `find_skill`, traverses it and
returns a plan."*

Click **Knowledge graph** in the header — pan around the explorer for 5 seconds.

## Beat 1 — Simple data question + the traversal map (2 min)

Paste:
> **Which countries host the most Sudanese refugees? Keep it brief.**

While it runs, narrate the activity panel: *"Find Skill is the graph traversal —
~40 nodes, 2 round-trips, under a second. It came back with the right Genie space,
the exact SQL pattern, and the chart recipe. One Genie call, no file reads."*

When the answer lands: open the **Knowledge-graph traversal** chip in the dock —
scroll-zoom in, drag a node, hit **⌖ Fit**. *"This is the agent's reasoning,
inspectable. Seeds in pink, the SQL pattern it pulled, the rule nodes it honored."*

## Beat 2 — The "why" lives in the graph too (1.5 min)

Paste:
> **Why does the same nationality get different asylum outcomes in different European countries?**

Say: *"This isn't a SQL question — it's an insight question. The graph carries
Findings with the methodology: the 'asylum lottery', fair-cohort rules (first-instance
decisions only, Europe allow-list, recognition rate not raw totals). The agent
answers from the graph's why-nodes and backs it with a fresh Genie pull."*

## Beat 3 — Scroll-driven essay (2 min)

Paste (also a suggested question on the home screen):
> **Build a scroll-driven narrative essay on the asylum lottery.**

While it runs (~2–3 min): show the home screen's suggested questions in a second
chat, or revisit the explorer. When done, open the artifact and **scroll slowly**:
*"Editorial scrollytelling — the sticky chart changes state as the story advances.
Every number is computed from the data, injected into the template; the agent
hand-writes none of them."*

## Beat 4 — Executive deck (2 min)

Paste:
> **Build a 6-slide deck on the global refugee picture at end-2024 — cover, top hosting countries, top origins, the trend since 2015, one chart slide, and a closing.**

When done, download the PPTX and open it: *"Native PowerPoint charts — editable,
not screenshots. Brand template with embedded fonts. The deck spec is JSON the
agent emits; the graph told it which slide types and chart kinds fit."*

## Beat 5 — Analyst handoff: a real notebook (1.5 min)

Paste:
> **Do a deep-dive analysis of where Sudanese refugees fled to and save it as a Databricks notebook for further exploration.**

Say: *"The agent doesn't dead-end in chat — it writes a real Databricks notebook
into the workspace and links it. Your analysts pick up exactly where it stopped."*
Click the notebook link when it appears.

## Beat 6 — The receipts (1 min, close)

Say: *"Same five questions on the old file-walking agent and on this one:
**3.46M input tokens → 1.45M — minus 58%**. Infographics 2.3× faster. The graph
doesn't just route better — it's cheaper every single turn, and the gap widens as
the knowledge base grows. Files don't scale; graphs do."*

End on the 738-node explorer zoomed out.

---

### Fallbacks
- Endpoint cold / slow: re-use a pre-generated chat from the history sidebar.
- Genie 429: say *"rate-limited Genie — the agent retries and falls back to Spark
  SQL"*; switch to the pre-generated artifact tab.
- Deck/PPTX wait: pre-generate one before the demo and open from the dock.

### Timing
~10 minutes total. Drop Beat 2 first if squeezed; never drop Beat 1 (the traversal
map is the differentiator) or Beat 6 (the numbers).

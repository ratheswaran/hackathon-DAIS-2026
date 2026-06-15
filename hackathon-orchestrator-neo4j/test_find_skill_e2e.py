"""End-to-end test: a real gpt-5.5 DeepAgent traverses the Neo4j knowledge graph
via find_skill and plans an answer — NO skill files, NO Lakebase.

This is the focused proof that the ONE swap works against the live stack:
  ChatDatabricks(gpt-5-external-provider == gpt-5.5)  +  find_skill (KG traversal
  against Aura, query embedded with databricks-gte-large-en)  +  InMemoryStore.

Run (creds come from workspace_config.yml unless set in env):
    .venv-test/bin/python test_find_skill_e2e.py
    .venv-test/bin/python test_find_skill_e2e.py "your question"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _load_cfg() -> dict:
    cfg = yaml.safe_load((_HERE / "workspace_config.yml").read_text())
    db = cfg.get("databricks", {})
    neo = cfg.get("neo4j", {})
    os.environ.setdefault("DATABRICKS_HOST", db.get("host", ""))
    os.environ.setdefault("DATABRICKS_TOKEN", db.get("token", ""))
    os.environ.setdefault("NEO4J_URI", neo.get("uri", ""))
    os.environ.setdefault("NEO4J_USER", neo.get("user", ""))
    os.environ.setdefault("NEO4J_PASSWORD", neo.get("password", ""))
    os.environ.setdefault("NEO4J_DATABASE", neo.get("database", ""))
    os.environ.setdefault("BRAIN_EMBED_BACKEND", "databricks")
    os.environ.setdefault("BRAIN_EMBED_ENDPOINT", neo.get("embed_endpoint", "databricks-gte-large-en"))
    os.environ.setdefault("BRAIN_EMBED_DIM", "1024")
    os.environ.setdefault("BRAIN_EMBED_BATCH", "1")
    return cfg


def main():
    cfg = _load_cfg()
    llm_endpoint = cfg.get("serving", {}).get("llm_endpoint_name", "gpt-5-external-provider")
    question = " ".join(sys.argv[1:]) or (
        "I want to show how an Afghan asylum-seeker's chance of getting refugee "
        "status depends on which European country they apply to. Which Genie "
        "space and SQL do I use, what gotchas must I honor, and what chart?"
    )

    from databricks_langchain import ChatDatabricks
    from deepagents import create_deep_agent
    from langgraph.store.memory import InMemoryStore
    from tools.find_skill import build_find_skill_tool

    print(f"== building find_skill (KG traversal → Aura) ==")
    find_skill = build_find_skill_tool(
        embedding_endpoint=os.environ["BRAIN_EMBED_ENDPOINT"],
        result_k=8,
        workspace_client=None,     # no Volume upload in the local harness
        render_graph=False,
    )

    print(f"== building deep agent on {llm_endpoint} (gpt-5.5) ==\n")
    # NOTE: gpt-5.5 (reasoning model) only supports the default temperature (1);
    # passing temperature=0 → 400 "unsupported_value". The production
    # orchestrator doesn't set temperature, so it's unaffected.
    model = ChatDatabricks(endpoint=llm_endpoint)
    agent = create_deep_agent(
        model=model,
        tools=[find_skill],
        system_prompt=(
            "You are a Databricks data-analytics orchestrator for UNHCR refugee "
            "data. You have NO skill files — call find_skill(query) to get the "
            "plan (Genie space, SQL, gotchas, metric, chart/deck, the why). "
            "Always call find_skill first, then summarise the PLAN for the user: "
            "name the Genie space + space_id, the SQL pattern, the gotchas to "
            "honor, and the recommended chart + tool. Do not invent space IDs."
        ),
        store=InMemoryStore(),
    )

    print(f"USER: {question}\n" + "=" * 80)
    saw_find_skill = False
    final = ""
    for chunk in agent.stream({"messages": [{"role": "user", "content": question}]},
                              {"configurable": {"thread_id": "e2e-1"}},
                              stream_mode="values"):
        msgs = chunk.get("messages", [])
        if not msgs:
            continue
        last = msgs[-1]
        # tool call by the model
        for tc in getattr(last, "tool_calls", None) or []:
            print(f"\n>>> TOOL CALL: {tc['name']}({tc['args']})")
            if tc["name"] == "find_skill":
                saw_find_skill = True
        # tool result
        if last.__class__.__name__ == "ToolMessage":
            body = str(last.content)
            print(f"\n<<< find_skill PLAN ({len(body)} chars):\n{body[:2600]}"
                  + (" …[truncated]" if len(body) > 2600 else ""))
        # assistant text
        elif last.__class__.__name__ == "AIMessage" and isinstance(last.content, str) and last.content.strip():
            final = last.content

    print("\n" + "=" * 80)
    print("FINAL ANSWER (gpt-5.5, grounded in the graph plan):\n")
    print(final)
    print("\n" + "=" * 80)
    print(f"RESULT: find_skill called = {saw_find_skill} · "
          f"answer produced = {bool(final.strip())}")
    if not saw_find_skill:
        print("WARN: agent did not call find_skill — check the tool wiring/prompt.")


if __name__ == "__main__":
    main()

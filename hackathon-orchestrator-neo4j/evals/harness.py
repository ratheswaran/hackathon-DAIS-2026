"""Local eval harness — runs the PRODUCTION agent graph in-process.

Builds the exact agent that Model Serving runs (same prompts, tool factories,
middleware, subagents, LakebaseVariableStore over the real Lakebase, live
Neo4j find_skill, live Genie) by importing ``deploy_orchestrator_agent`` and
calling ``create_production_agent()`` with local substitutions:

  - checkpointer: ``InMemorySaver``  (per-case threads are fresh; multi-turn
    cases reuse the same thread within a run)
  - memory_store: ``InMemoryStore``  (langmem user-prefs — empty locally)
  - workspace_client: PAT client from workspace_config.yml (the SP/OBO split
    collapses to one identity locally)

Everything the model *sees* — system prompts, tool schemas, tool results —
is byte-identical to production, so token measurements transfer. What does
NOT transfer: serving-container cold start and the predict_stream wrapper
(user-prefs block ~125 tokens, episodic recall — both disabled/empty on this
fork anyway).

Metrics are captured with a LangChain callback handler: one record per LLM
call (tokens via usage_metadata, wall-clock, message count) and per tool call
(name, wall-clock, result size). Callbacks propagate into subagent graphs, so
python-analyst / data-viz LLM calls are counted too.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def load_env() -> dict:
    """Populate env from workspace_config.yml (same keys the endpoint gets)."""
    import yaml

    cfg = yaml.safe_load((_ROOT / "workspace_config.yml").read_text())
    db = cfg.get("databricks", {})
    neo = cfg.get("neo4j", {})
    os.environ.setdefault("DATABRICKS_HOST", db.get("host", ""))
    os.environ.setdefault("DATABRICKS_TOKEN", db.get("token", ""))
    os.environ.setdefault("NEO4J_URI", neo.get("uri", ""))
    os.environ.setdefault("NEO4J_USER", neo.get("user", ""))
    os.environ.setdefault("NEO4J_PASSWORD", neo.get("password", ""))
    os.environ.setdefault("NEO4J_DATABASE", neo.get("database", ""))
    os.environ.setdefault("BRAIN_EMBED_BACKEND", "databricks")
    os.environ.setdefault(
        "BRAIN_EMBED_ENDPOINT", neo.get("embed_endpoint", "databricks-gte-large-en")
    )
    os.environ.setdefault("BRAIN_EMBED_DIM", "1024")
    os.environ.setdefault("BRAIN_EMBED_BATCH", "1")
    return cfg


# ---------------------------------------------------------------------------
# Metrics callback
# ---------------------------------------------------------------------------

def _msg_chars(messages) -> int:
    total = 0
    for batch in messages:
        for m in batch if isinstance(batch, list) else [batch]:
            total += len(str(getattr(m, "content", m)))
    return total


from langchain_core.callbacks import BaseCallbackHandler


class MetricsCallback(BaseCallbackHandler):
    """Records every LLM + tool call (tokens, wall-clock, result sizes)."""

    raise_error = False
    run_inline = True

    def __init__(self) -> None:
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self._open_llm: dict[Any, dict] = {}
        self._open_tool: dict[Any, dict] = {}

    # -- chat model -------------------------------------------------------
    def on_chat_model_start(self, serialized, messages, *, run_id, **kw):
        self._open_llm[run_id] = {
            "t0": time.time(),
            "n_messages": sum(len(b) for b in messages),
            "input_chars": _msg_chars(messages),
        }

    def on_llm_start(self, serialized, prompts, *, run_id, **kw):
        self._open_llm[run_id] = {
            "t0": time.time(),
            "n_messages": len(prompts),
            "input_chars": sum(len(p) for p in prompts),
        }

    def on_llm_end(self, response, *, run_id, **kw):
        rec = self._open_llm.pop(run_id, {"t0": time.time()})
        usage = {}
        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)
            usage = dict(getattr(msg, "usage_metadata", None) or {})
        except Exception:
            pass
        if not usage:
            usage = dict((getattr(response, "llm_output", None) or {}).get("usage", {}) or {})
        self.llm_calls.append(
            {
                "duration_s": round(time.time() - rec["t0"], 2),
                "n_messages": rec.get("n_messages"),
                "input_chars": rec.get("input_chars"),
                "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
                "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cache_read": (usage.get("input_token_details") or {}).get("cache_read"),
            }
        )

    def on_llm_error(self, error, *, run_id, **kw):
        rec = self._open_llm.pop(run_id, {"t0": time.time()})
        self.llm_calls.append(
            {
                "duration_s": round(time.time() - rec["t0"], 2),
                "error": str(error)[:300],
            }
        )

    # -- tools --------------------------------------------------------------
    def on_tool_start(self, serialized, input_str, *, run_id, **kw):
        name = (serialized or {}).get("name") or kw.get("name") or "?"
        self._open_tool[run_id] = {"t0": time.time(), "name": name}

    def on_tool_end(self, output, *, run_id, **kw):
        rec = self._open_tool.pop(run_id, None)
        if rec is None:
            return
        text = str(getattr(output, "content", output))
        self.tool_calls.append(
            {
                "name": rec["name"],
                "duration_s": round(time.time() - rec["t0"], 2),
                "output_chars": len(text),
                "output_head": text[:300],
            }
        )

    def on_tool_error(self, error, *, run_id, **kw):
        rec = self._open_tool.pop(run_id, None)
        if rec is None:
            return
        self.tool_calls.append(
            {
                "name": rec["name"],
                "duration_s": round(time.time() - rec["t0"], 2),
                "error": str(error)[:300],
            }
        )

    # -- summary ------------------------------------------------------------
    def summary(self) -> dict:
        ok = [c for c in self.llm_calls if "error" not in c]
        in_tok = [c["input_tokens"] for c in ok if c.get("input_tokens")]
        out_tok = [c["output_tokens"] for c in ok if c.get("output_tokens")]
        return {
            "llm_calls": len(self.llm_calls),
            "llm_errors": len(self.llm_calls) - len(ok),
            "input_tokens": sum(in_tok) if in_tok else None,
            "output_tokens": sum(out_tok) if out_tok else None,
            "total_tokens": (sum(in_tok) + sum(out_tok)) if (in_tok and out_tok) else None,
            "max_input_tokens_call": max(in_tok) if in_tok else None,
            "llm_time_s": round(sum(c["duration_s"] for c in self.llm_calls), 1),
            "tool_time_s": round(sum(t["duration_s"] for t in self.tool_calls), 1),
            "tool_call_count": len(self.tool_calls),
        }


# ---------------------------------------------------------------------------
# Agent build
# ---------------------------------------------------------------------------

_BUILT: dict[str, Any] = {}


def build_agent(force: bool = False):
    """Import the deploy module and assemble the production agent locally."""
    if _BUILT.get("graph") is not None and not force:
        return _BUILT["graph"], _BUILT["orch"]

    cfg = load_env()

    import mlflow

    # No autolog locally — traces would add latency noise + remote logging.
    try:
        mlflow.langchain.autolog(disable=True)
    except Exception:
        pass

    import psycopg
    from databricks.sdk import WorkspaceClient
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    # The deploy script's first notebook cell calls dbutils (Databricks-only
    # global). Shim it: widgets.text is a no-op, widgets.get raises → the
    # _deploy_*_enabled() guards fall through to env vars, which we pin off.
    import builtins

    class _ShimWidgets:
        def text(self, *a, **k):
            return None

        def get(self, name):
            raise KeyError(name)

    class _ShimDbutils:
        widgets = _ShimWidgets()

    builtins.dbutils = _ShimDbutils()
    os.environ["DEPLOY_V2"] = "0"
    os.environ["DEPLOY_V3"] = "0"

    import deploy_orchestrator_agent as orch

    # --- local substitutions for what _init_checkpointer does in serving ---
    host = os.environ["DATABRICKS_HOST"]
    if not host.startswith("http"):
        host = f"https://{host}"
    wc = WorkspaceClient(host=host, token=os.environ["DATABRICKS_TOKEN"])
    orch._workspace_client = wc
    orch._obo_workspace_client = None

    lakebase_url = cfg["lakebase"]["url"]
    from variable_store.lakebase_store import configure as _configure_vs

    _configure_vs(connection_factory=lambda: psycopg.connect(lakebase_url))
    orch._DUCKDB_LAKEBASE_DSN = orch.OrchestratorResponsesAgent._url_to_duckdb_dsn(
        lakebase_url
    )
    orch.memory_store = InMemoryStore()

    graph = orch.AGENT.create_production_agent(InMemorySaver())
    _BUILT.update({"graph": graph, "orch": orch})
    return graph, orch


# ---------------------------------------------------------------------------
# Case runner
# ---------------------------------------------------------------------------

def _extract_answer(messages) -> str:
    for m in reversed(messages or []):
        if m.__class__.__name__ == "AIMessage":
            c = m.content
            if isinstance(c, str) and c.strip():
                return c
            if isinstance(c, list):
                text = " ".join(
                    b.get("text", "") for b in c if isinstance(b, dict)
                ).strip()
                if text:
                    return text
    return ""


def _transcript(messages) -> list[dict]:
    """Orchestrator-level tool-call transcript (subagent inner calls excluded)."""
    out = []
    for m in messages or []:
        for tc in getattr(m, "tool_calls", None) or []:
            args = json.dumps(tc.get("args", {}), default=str)
            out.append(
                {
                    "name": tc.get("name"),
                    "args": args[:300] + ("…" if len(args) > 300 else ""),
                }
            )
    return out


def run_case(graph, case: dict, recursion_limit: int = 100) -> dict:
    """Run one eval case (possibly multi-turn). Returns the raw result record."""
    cb = MetricsCallback()
    thread_id = f"eval-{case['id']}-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [cb],
        "recursion_limit": recursion_limit,
    }

    turns_out: list[dict] = []
    final_messages = None
    error: Optional[str] = None
    t_case = time.time()
    for turn in case["turns"]:
        t0 = time.time()
        try:
            for chunk in graph.stream(
                {"messages": [{"role": "user", "content": turn}]},
                config,
                stream_mode="values",
            ):
                if chunk.get("messages"):
                    final_messages = chunk["messages"]
        except Exception as e:  # noqa: BLE001 — record, don't crash the suite
            error = f"{type(e).__name__}: {e}"
        turns_out.append(
            {
                "user": turn,
                "latency_s": round(time.time() - t0, 1),
                "answer": _extract_answer(final_messages),
                "error": error,
            }
        )
        if error:
            break

    return {
        "id": case["id"],
        "category": case.get("category"),
        "turns": turns_out,
        "latency_s": round(time.time() - t_case, 1),
        "metrics": cb.summary(),
        "llm_calls_detail": cb.llm_calls,
        "tool_calls_detail": cb.tool_calls,
        "tool_sequence": [t["name"] for t in cb.tool_calls],
        "orchestrator_tool_calls": _transcript(final_messages),
        "error": error,
    }

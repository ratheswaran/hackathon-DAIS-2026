# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy: Orchestrator Agent (Direct Data + 2 Subagents)
# MAGIC
# MAGIC Orchestrator with direct SQL/Genie data retrieval and two specialist
# MAGIC subagents, wrapped in MLflow `ResponsesAgent` for Model Serving.
# MAGIC
# MAGIC

# COMMAND ----------

dbutils.widgets.text("DEPLOY_V3", "1")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Dependencies
# MAGIC
# MAGIC This notebook expects all Python packages to be supplied via the **Environment**
# MAGIC side panel (Dependencies → Add → `-r requirements.txt`). The `requirements.txt`
# MAGIC file is at the same workspace path as this notebook.
# MAGIC
# MAGIC No `%pip install` cells run here — installing in-cell forks a pip resolver
# MAGIC inside the running kernel and adds memory pressure for no benefit when the
# MAGIC Environment panel can install the same packages before kernel start.
# MAGIC
# MAGIC If a dep is missing at import time, add it to `requirements.txt`, re-Apply
# MAGIC the environment, then rerun this notebook from the top.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 2: Imports — bisect mode
# MAGIC
# MAGIC Each import group lives in its own cell, prints a marker on success, and
# MAGIC `flush=True` so the print survives a kernel SIGKILL. When a cell fails,
# MAGIC the last `[bisect:N OK]` line tells you which group crashed.
# MAGIC
# MAGIC Run cells one at a time, top to bottom. Note which cell number first
# MAGIC fails to print its OK marker — that's the culprit group.

# COMMAND ----------

# Bisect 1/10 — stdlib
import os
import io
import re
import sys
import json
import uuid
import time
import logging
import hashlib
import textwrap
import contextlib
import threading
import tempfile
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta
from typing import TypedDict, Callable, Dict, Any, Generator, Optional, List, Annotated, Tuple
from pathlib import Path
print("[bisect:1/10 stdlib] OK", flush=True)

# COMMAND ----------

# Bisect 2/10 — pandas
import pandas as pd
print("[bisect:2/10 pandas] OK", flush=True)

# COMMAND ----------

# Bisect 3/10 — langchain_core (messages, tools, runnables)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
print("[bisect:3/10 langchain_core] OK", flush=True)

# COMMAND ----------

# Bisect 4/10 — langchain.agents.middleware
from langchain.agents.middleware import ModelRequest, ModelResponse, AgentMiddleware
print("[bisect:4/10 langchain.agents.middleware] OK", flush=True)

# COMMAND ----------

# Bisect 5/10 — langgraph.prebuilt
from langgraph.prebuilt import InjectedStore
print("[bisect:5/10 langgraph.prebuilt] OK", flush=True)

# COMMAND ----------

# Bisect 6/10 — databricks.sdk (WorkspaceClient + service.workspace + service.compute)
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat, Language
from databricks.sdk.service.compute import Language as ComputeLanguage
print("[bisect:6/10 databricks.sdk] OK", flush=True)

# COMMAND ----------

# Bisect 7/10 — databricks_langchain.ChatDatabricks
# Prior OOM trace pointed here: databricks_langchain → databricks_ai_bridge.lakebase → psycopg.pq
# If the crash is module imports, this is the most likely cell to die.
from databricks_langchain import ChatDatabricks
print("[bisect:7/10 databricks_langchain.ChatDatabricks] OK", flush=True)

# COMMAND ----------

# Bisect 8/10 — deepagents (create_deep_agent + backends)
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend
print("[bisect:8/10 deepagents] OK", flush=True)

# COMMAND ----------

# Bisect 9/10 — langgraph.checkpoint.base
from langgraph.checkpoint.base import BaseCheckpointSaver
print("[bisect:9/10 langgraph.checkpoint.base] OK", flush=True)

# COMMAND ----------

# Bisect 10/10 — mlflow + ResponsesAgent + types.responses
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
    output_to_responses_items_stream,
)
print("[bisect:10/10 mlflow] OK", flush=True)

# COMMAND ----------

# All imports cleared bisect — set up logger + continue with module config.
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
print("[bisect:DONE] all import groups loaded; continuing with config", flush=True)


# --- Workspace Config Loader ---
def _load_workspace_config():
    """Load workspace_config.yml — search common locations."""
    import yaml
    from pathlib import Path
    _this_file = globals().get("__file__")
    candidates = [
        Path("workspace_config.yml"),
        Path("/Workspace") / os.environ.get("NOTEBOOK_DIR", "") / "workspace_config.yml",
    ]
    if _this_file:
        _parent = Path(_this_file).parent
        candidates.insert(0, _parent / "workspace_config.yml")
        # MLflow model artifacts: code/ is a sibling of the model file
        candidates.insert(1, _parent / "code" / "workspace_config.yml")
        # One level up (e.g. artifacts/model/code/workspace_config.yml)
        candidates.insert(2, _parent.parent / "workspace_config.yml")
        candidates.insert(3, _parent.parent / "code" / "workspace_config.yml")
    for candidate in candidates:
        if candidate and candidate.exists():
            with open(candidate) as f:
                cfg = yaml.safe_load(f)
                logger.info(f"Loaded workspace_config.yml from {candidate}")
                return cfg
    logger.warning("workspace_config.yml not found in any search path")
    return {}


_CFG = _load_workspace_config()

# --- Configuration (env var → workspace_config.yml) ---
SKILLS_DIR = Path("skills")

_db_cfg = _CFG.get("databricks", {})
_serving_cfg = _CFG.get("serving", {})
_compute_cfg = _CFG.get("compute", {})
_genie_cfg = _CFG.get("genie", {})
_vs_cfg = _CFG.get("vector_search", {})
_agent_cfg = _CFG.get("agent", {})

DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", _db_cfg.get("host", ""))
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", _db_cfg.get("token", ""))

LLM_ENDPOINT_NAME = os.environ.get("LLM_ENDPOINT_NAME", _serving_cfg.get("llm_endpoint_name", ""))
LLM_ENDPOINT_NAME_LIGHT = (
    os.environ.get("LLM_ENDPOINT_NAME_LIGHT", _serving_cfg.get("llm_endpoint_name_light", ""))
    or LLM_ENDPOINT_NAME
)
SQL_WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID", _compute_cfg.get("sql_warehouse_id", ""))
CLUSTER_ID = os.environ.get("CLUSTER_ID", _compute_cfg.get("cluster_id", ""))

WORKSPACE_URL = os.environ.get("WORKSPACE_URL", _db_cfg.get("workspace_url", ""))
if not WORKSPACE_URL:
    WORKSPACE_URL = f"https://{DATABRICKS_HOST}"
WORKSPACE_URL = WORKSPACE_URL.rstrip("/")
if not WORKSPACE_URL.startswith("https://"):
    WORKSPACE_URL = f"https://{WORKSPACE_URL}"


def _parse_workspace_host(host: str) -> tuple[str, str] | tuple[None, None]:
    """Return (workspace_id, shard) parsed from a Databricks host string.

    Accepts e.g. ``adb-<workspace-id>.5.azuredatabricks.net`` and returns
    ``("<workspace-id>", "5")``. Returns ``(None, None)`` on non-matching
    hosts (e.g. custom domains, lab workspaces with different naming).
    """
    if not host:
        return None, None
    stripped = host.replace("https://", "").replace("http://", "").rstrip("/")
    m = re.match(r"^adb-(\d+)\.(\d+)\.azuredatabricks\.net$", stripped)
    if m:
        return m.group(1), m.group(2)
    return None, None


WORKSPACE_ID, WORKSPACE_SHARD = _parse_workspace_host(DATABRICKS_HOST)


def _derive_app_url(host: str, app_name: str | None) -> str | None:
    """Build a Databricks Apps URL from the workspace host + app name.

    Pattern (Azure): ``https://{app}-{ws_id}.{shard}.azure.databricksapps.com``.
    Returns ``None`` if either input is missing or the host doesn't match
    the known ``adb-*.azuredatabricks.net`` pattern (callers should then
    fall back to an explicit ``app.url`` override from config).
    """
    if not app_name:
        return None
    ws_id, shard = _parse_workspace_host(host)
    if not ws_id or not shard:
        return None
    return f"https://{app_name}-{ws_id}.{shard}.azure.databricksapps.com"


_APP_CFG = _CFG.get("app", {}) or {}
# Explicit url wins; otherwise derive from host + app.name so the same config
# works across work / lab / prod without a hardcoded per-workspace URL.
APP_URL = (
    os.environ.get("APP_URL")
    or _APP_CFG.get("url")
    or _derive_app_url(DATABRICKS_HOST, _APP_CFG.get("name"))
    or None
)  # None when not configured — chart_url omitted from render_chart return

GENIE_TIMEOUT_SECONDS = int(os.environ.get(
    "GENIE_TIMEOUT_SECONDS", _genie_cfg.get("timeout_seconds", ""),
))

_TRACING_ENABLED = str(os.environ.get(
    "ENABLE_MLFLOW_TRACING", _CFG.get("mlflow", {}).get("enable_tracing", True),
)).lower() == "true"

# Semantic cache configuration (Direct Access Vector Search)
SEMANTIC_CACHE_ENABLED = str(os.environ.get(
    "SEMANTIC_CACHE_ENABLED", _vs_cfg.get("cache_enabled", ""),
)).lower() == "true"
SEMANTIC_CACHE_ENDPOINT_NAME = os.environ.get("VS_CACHE_ENDPOINT", _vs_cfg.get("cache_endpoint", ""))
SEMANTIC_CACHE_INDEX_NAME = os.environ.get("VS_CACHE_INDEX", _vs_cfg.get("cache_index", ""))
SEMANTIC_CACHE_EMBEDDING_ENDPOINT = os.environ.get(
    "VS_CACHE_EMBEDDING_ENDPOINT", _vs_cfg.get("embedding_endpoint", ""),
)
SEMANTIC_CACHE_SIMILARITY_THRESHOLD = float(os.environ.get(
    "SEMANTIC_CACHE_SIMILARITY_THRESHOLD", _vs_cfg.get("cache_similarity_threshold", ""),
))
SEMANTIC_CACHE_TTL_HOURS = int(os.environ.get(
    "SEMANTIC_CACHE_TTL_HOURS", _vs_cfg.get("cache_ttl_hours", ""),
))

# Episodic memory removed for hackathon build — both write + recall paths are
# disabled per hackathon decisions doc (2026-05-13). All EPISODIC_VS_* vars
# stay assigned to inert defaults so any leftover references compile but no-op.
EPISODIC_VS_ENABLED = False
EPISODIC_VS_ENDPOINT_NAME = ""
EPISODIC_VS_INDEX_NAME = ""
EPISODIC_VS_SCORE_THRESHOLD = 0.0
EPISODIC_VS_NUM_RESULTS = 0

# Langmem user preferences (hot-path memory, per-user namespace via PostgresStore).
# Read default from workspace_config.yml `user_prefs.enabled`; env var wins.
_user_prefs_cfg = _CFG.get("user_prefs", {}) or {}
USER_PREFS_ENABLED = str(os.environ.get(
    "USER_PREFS_ENABLED", _user_prefs_cfg.get("enabled", "true"),
)).lower() == "true"
USER_PREFS_NUM_RESULTS = int(os.environ.get(
    "USER_PREFS_NUM_RESULTS", _user_prefs_cfg.get("num_results", "3"),
))

# --- Neo4j skills-brain (find_skill) ---------------------------------------
# The find_skill tool reads NEO4J_* from env (injected at deploy from the
# `agent-secrets` secret scope, mirroring the SAP GraphRAG reference). The
# query embedding uses the SAME Databricks FM endpoint the graph was ingested
# with (default databricks-gte-large-en, 1024-dim) so query/index vectors
# match and no torch ships in the serving image. See the Neo4j skills-graph design.
_neo4j_cfg = _CFG.get("neo4j", {}) or {}
# brain/config.py reads NEO4J_URI/USER/PASSWORD/DATABASE directly from env; we
# only seed defaults here so local runs (config.yml) work without secrets.
for _k_env, _k_cfg in (("NEO4J_URI", "uri"), ("NEO4J_USER", "user"),
                       ("NEO4J_PASSWORD", "password"), ("NEO4J_DATABASE", "database")):
    if not os.environ.get(_k_env) and _neo4j_cfg.get(_k_cfg):
        os.environ[_k_env] = str(_neo4j_cfg.get(_k_cfg))
FIND_SKILL_EMBED_ENDPOINT = os.environ.get(
    "BRAIN_EMBED_ENDPOINT",
    _neo4j_cfg.get("embed_endpoint", _vs_cfg.get("embedding_endpoint", "databricks-gte-large-en")),
)
FIND_SKILL_RESULT_K = int(os.environ.get(
    "FIND_SKILL_RESULT_K", _neo4j_cfg.get("result_k", "6"),
))
FIND_SKILL_RENDER_GRAPH = str(os.environ.get(
    "FIND_SKILL_RENDER_GRAPH", _neo4j_cfg.get("render_graph", "true"),
)).lower() == "true"

# Module-level globals (populated during init)
model = None
memory_store = None
semantic_cache = None
_workspace_client = None      # SP-mode (stable identity for episodic memory,
                              # Vector Search reads, UC catalog list, Volume
                              # writes for charts).
_obo_workspace_client = None  # OBO-mode — minted with ModelServingUserCredentials()
                              # so per-call API uses the forwarded user token.
                              # Used by Genie / SQL-warehouse / notebook-write
                              # tools so row-level security flows to the user.
                              # See the OBO dual-client pattern.
_current_user_email = None
_uc_catalog_names: set = set()  # populated by _init_db() from UC catalogs.list()


def _get_current_user_email() -> str:
    """Get the current user's email, caching for subsequent calls."""
    global _current_user_email
    if _current_user_email is None and _workspace_client is not None:
        try:
            _current_user_email = _workspace_client.current_user.me().user_name
        except Exception:
            _current_user_email = "default_user"
    return _current_user_email or "default_user"


def _user_workspace_client():
    """Return the OBO-mode WorkspaceClient when available, else SP fallback.

    Used by tools that should execute under the calling user's identity
    (Genie, SQL warehouse, Workspace notebook write/run). The OBO client is
    backed by ``ModelServingUserCredentials()`` which reads
    ``X-Forwarded-Access-Token`` per call, so a single cached instance
    correctly serves N concurrent users — see the OBO dual-client pattern.

    Falls back to the SP client when:
      - Running locally (no Model Serving runtime, OBO bridge unavailable).
      - log_model validation runs in environments that don't forward a user
        token.
      - The forwarded token is absent (direct serving-endpoint UI calls).
    """
    if _obo_workspace_client is not None:
        return _obo_workspace_client
    return _workspace_client

current_date = datetime.now().strftime("%Y-%m-%d")

logger.info(f"Config: host={DATABRICKS_HOST}, llm={LLM_ENDPOINT_NAME}, warehouse={SQL_WAREHOUSE_ID}, cluster={CLUSTER_ID}")

# Episodic memory recall / format / log — now in helpers.episodic_memory

# --- Semantic Cache (Direct Access Vector Search) ---

class SemanticCache:
    """Semantic similarity cache using Databricks Vector Search (Direct Access).

    Uses DatabricksEmbeddings to compute vectors and the SDK to upsert/query
    a Direct Access index. No Delta Sync pipeline — writes are immediately queryable.
    """

    def __init__(
        self,
        enabled: bool,
        endpoint_name: str,
        index_name: str,
        embedding_endpoint: str,
        similarity_threshold: float,
        ttl_hours: int,
    ):
        self.enabled = enabled
        self.endpoint_name = endpoint_name
        self.index_name = index_name
        self.embedding_endpoint = embedding_endpoint
        self.similarity_threshold = similarity_threshold
        self.ttl_hours = ttl_hours
        self._embeddings = None

    def _get_embedding(self, text: str) -> list[float]:
        """Compute embedding vector via Databricks foundation model endpoint."""
        if self._embeddings is None:
            from databricks_langchain import DatabricksEmbeddings
            self._embeddings = DatabricksEmbeddings(endpoint=self.embedding_endpoint)
        return self._embeddings.embed_query(text)

    def _ensure_workspace_client(self):
        """Check that _workspace_client is available."""
        if _workspace_client is None:
            raise RuntimeError("WorkspaceClient not initialized — call _init_db() first")

    def get(self, question: str) -> Optional[str]:
        """Look up a semantically similar cached answer."""
        if not self.enabled:
            return None
        try:
            self._ensure_workspace_client()
            query_vector = self._get_embedding(question)
            logger.info(f"Semantic cache lookup: embedding dim={len(query_vector)}, index={self.index_name}")
            results = _workspace_client.vector_search_indexes.query_index(
                index_name=self.index_name,
                columns=["cache_key", "question", "answer_text", "created_at"],
                query_vector=query_vector,
                num_results=1,
            )

            if results.result and results.result.data_array:
                row = results.result.data_array[0]
                score = row[-1]  # similarity score is last column

                if score < self.similarity_threshold:
                    logger.info(f"Semantic cache MISS: score={score:.3f} < threshold={self.similarity_threshold}")
                    return None

                answer_text = row[2]
                created_at_str = row[3]

                # TTL check
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                        if datetime.now() - created_at > timedelta(hours=self.ttl_hours):
                            logger.info(f"Semantic cache expired: score={score:.3f}, age exceeded {self.ttl_hours}h")
                            return None
                    except ValueError:
                        pass

                logger.info(f"Semantic cache HIT: score={score:.3f}, matched='{row[1][:60]}...'")
                return answer_text

            logger.info("Semantic cache MISS: no results returned from index")
            return None
        except Exception as e:
            logger.error(f"Semantic cache get FAILED: {type(e).__name__}: {e}", exc_info=True)
            return None

    def store(self, question: str, answer_text: str):
        """Store a Q&A pair via Direct Access upsert (immediately queryable)."""
        if not self.enabled:
            return
        try:
            self._ensure_workspace_client()
            embedding = self._get_embedding(question)
            cache_key = hashlib.sha256(question.encode("utf-8")).hexdigest()

            _workspace_client.vector_search_indexes.upsert_data_vector_index(
                index_name=self.index_name,
                inputs_json=json.dumps([{
                    "cache_key": cache_key,
                    "question": question,
                    "answer_text": answer_text,
                    "embedding": embedding,
                    "created_at": datetime.now().isoformat(),
                }]),
            )
            logger.info(f"Stored in semantic cache: q='{question[:60]}...'")
        except Exception as e:
            logger.error(f"Semantic cache store FAILED: {type(e).__name__}: {e}", exc_info=True)


def _extract_tables_from_skills(skills_dir: Path) -> str:
    """Scan any bundled skill markdown for table definitions and return a list.

    Parses lines like ``### N. `catalog.schema.table` `` followed by
    ``**Description**: ...`` from a business_context.md (or any .md file under
    each skill directory).  Returns a bullet list suitable for prompt injection,
    e.g.::

        - `workspace.hackathon.facilities` — healthcare facilities

    NOTE: domain knowledge (the table inventory, schemas, gotchas) is now served
    at runtime by the find_skill graph + the Genie space rather than bundled
    domain skills, so this scanner usually finds nothing and returns the
    find_skill fallback below — that's expected.
    """
    table_header_re = re.compile(r"^###\s+\d+\.\s+`([^`]+)`")
    tables: list[str] = []

    if not skills_dir.exists():
        return _SKILL_TABLES_FALLBACK

    for md_file in sorted(skills_dir.rglob("*.md")):
        if md_file.name.lower() in ("skill.md", "sql_patterns.md"):
            continue  # only parse context/schema files
        try:
            lines = md_file.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            m = table_header_re.match(line.strip())
            if not m:
                continue
            table_name = m.group(1)
            # Grab first non-empty sentence from the Description block
            desc = ""
            for j in range(i + 1, min(i + 6, len(lines))):
                text = lines[j].strip()
                if text.startswith("**Description**:"):
                    text = text.replace("**Description**:", "").strip()
                    text = text.replace("[Description]", "").strip()
                if text and not text.startswith("#") and not text.startswith("|") and not text.startswith("["):
                    # Keep only the first sentence to avoid bloating the prompt
                    first_sentence = text.split(". ")[0].rstrip(".")
                    desc = first_sentence
                    break
            tables.append(f"  - `{table_name}` — {desc}" if desc else f"  - `{table_name}`")

    return "\n".join(tables) if tables else _SKILL_TABLES_FALLBACK


# When no tables are bundled (the normal case — domain knowledge is served by
# the find_skill graph + Genie space), inject a directive instead of an empty
# allow-list so the prompt never reads "Only use the following tables:" with
# nothing after it.
_SKILL_TABLES_FALLBACK = (
    "  - (call find_skill first — it returns the table inventory, schemas, "
    "and gotchas for the active domain; do not assume a fixed table set)"
)

# Pre-extract tables for prompt injection (resolved again at agent init if skills_dir changes)
_SKILL_TABLES_TEXT = _extract_tables_from_skills(SKILLS_DIR)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 3: Middleware

# COMMAND ----------

class ModelServingToolFilterMiddleware(AgentMiddleware):
    """Whitelist tools safe for Model Serving containers."""

    ALLOWED_TOOLS = {
        # Orchestrator data retrieval (direct)
        "ask_genie_space", "run_spark_sql",
        # v2 analysis + exploration
        "describe_dataframe", "query_stored_dfs", "think_tool",
        # Python execution
        "run_python_code", "run_python_notebook", "save_python_notebook",
        # Visualization (replaced render_chart with compose_infographic — hackathon decision 2026-05-13).
        # compose_infographic = native D3 scene engine (single chart or multi-panel report story);
        # compose_story = freehand bespoke scrollytelling escape hatch (data-injection only, no exec).
        "compose_infographic", "compose_story",
        # Office-suite document generation (docx/xlsx/csv/pdf) — added 2026-05-15
        # after the pptx-via-run_python_code trap (tr-83d056e1a485c06f8b19df47db7f08e3).
        "compose_document",
        # Presentation decks (RA-branded .pptx native charts + HTML preview) —
        # wired 2026-05-31. Additive to compose_document; see compose-pptx skill.
        "compose_deck",
        # Variable Store (shared across all agents)
        "store_dataframe", "list_dataframes",
        # Neo4j skills-brain — replaces filesystem skill retrieval. One graph
        # query returns the relevant skill chunks + routed skill folders.
        "find_skill",
        # Langmem hot-path user preferences (orchestrator-only write tool;
        # reads happen in predict_stream via _retrieve_user_prefs, no tool).
        "save_user_preference",
        # DeepAgent built-in (Store-backed, no local filesystem needed)
        "write_todos", "read_todos",
        # DeepAgent built-in (routed to DatabricksVolumesBackend, not local FS).
        # 2026-06-12 eval round: write_file/edit_file/glob/grep removed from
        # the model-visible set — nothing on this fork uses them (skills are
        # graph-only via find_skill; documents go through compose_*; notebooks
        # through save/run_python_notebook) and their schemas cost ~1k tokens
        # on every LLM call. read_file + ls stay as the volume-browse fallback.
        "read_file", "ls",
        # Subagent delegation
        "task",
    }

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        filtered_tools = [t for t in request.tools if t.name in self.ALLOWED_TOOLS]
        if len(filtered_tools) != len(request.tools):
            removed = {t.name for t in request.tools} - self.ALLOWED_TOOLS
            logger.info(f"ToolFilter: removed {removed}")
        return handler(request.override(tools=filtered_tools))


class FailedToolPruningMiddleware(AgentMiddleware):
    """Remove failed tool call + response pairs from model context to save tokens."""

    _ERROR_KEYWORDS = ["error", "exception", "timed out", "not found", "failed"]

    def _is_error_response(self, content: str) -> bool:
        return any(kw in content.lower() for kw in self._ERROR_KEYWORDS)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        messages = list(request.messages)

        # Build a map: AI message index → list of its tool response indices.
        # An AI message with tool_calls is followed by 1+ tool response messages.
        ai_tool_groups: list[tuple[int, list[int]]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_call_ids = {tc["id"] if isinstance(tc, dict) else getattr(tc, "id", None)
                                 for tc in msg.tool_calls}
                tool_response_indices = []
                j = i + 1
                while j < len(messages):
                    resp = messages[j]
                    resp_tc_id = getattr(resp, "tool_call_id", None)
                    if resp_tc_id and resp_tc_id in tool_call_ids:
                        tool_response_indices.append(j)
                        j += 1
                    else:
                        break
                ai_tool_groups.append((i, tool_response_indices))
                i = j
            else:
                i += 1

        # Identify groups where ALL tool responses are errors
        failed_indices = set()
        for ai_idx, resp_indices in ai_tool_groups:
            if resp_indices and all(
                self._is_error_response(str(messages[ri].content))
                for ri in resp_indices
            ):
                failed_indices.add(ai_idx)
                failed_indices.update(resp_indices)

        if not failed_indices:
            return handler(request)

        # Keep the most recent failed group for context
        failed_ai_indices = sorted(
            i for i in failed_indices if hasattr(messages[i], "tool_calls")
        )
        if failed_ai_indices:
            last_ai = failed_ai_indices[-1]
            # Find its group and keep it
            for ai_idx, resp_indices in ai_tool_groups:
                if ai_idx == last_ai:
                    failed_indices.discard(ai_idx)
                    for ri in resp_indices:
                        failed_indices.discard(ri)
                    break

        if not failed_indices:
            return handler(request)

        logger.info(f"FailedToolPruning: removing {len(failed_indices)} messages")
        filtered = [m for i, m in enumerate(messages) if i not in failed_indices]
        return handler(request.override(messages=filtered))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 4: Tools

# COMMAND ----------

# =============================================================================
# 4a. Infrastructure Helpers
# =============================================================================

def _ensure_warehouse_running(w, warehouse_id, timeout_seconds=300):
    """Check if SQL warehouse is running; start it if stopped."""
    try:
        wh = w.warehouses.get(id=warehouse_id)
        state = wh.state.value if wh.state else "UNKNOWN"

        if state == "RUNNING":
            return None

        if state in ("STOPPED", "STOPPING"):
            logger.info(f"SQL warehouse {warehouse_id} is {state}, starting...")
            w.warehouses.start(id=warehouse_id)

        # Poll until running
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            time.sleep(10)
            wh = w.warehouses.get(id=warehouse_id)
            current = wh.state.value if wh.state else "UNKNOWN"
            if current == "RUNNING":
                return None
            if current in ("DELETED", "DELETING"):
                return f"Warehouse is {current}"

        return f"Warehouse not ready after {timeout_seconds}s"
    except Exception as e:
        return f"Warehouse check failed: {e}"


def _ensure_cluster_running(w, cluster_id, timeout_seconds=300):
    """Check cluster state; start if terminated."""
    try:
        info = w.clusters.get(cluster_id)
        state = str(info.state)
        if "RUNNING" in state:
            return None
        if "TERMINATED" in state:
            w.clusters.start(cluster_id)
            logger.info(f"Starting cluster {cluster_id}...")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            info = w.clusters.get(cluster_id)
            state = str(info.state)
            if "RUNNING" in state:
                return None
            if "ERROR" in state:
                return f"Cluster in ERROR state"
            time.sleep(10)
        return f"Cluster not ready after {timeout_seconds}s"
    except Exception as e:
        return f"Cluster check failed: {e}"


AUDIT_LOG_TABLE = os.environ.get("AGENT_AUDIT_LOG_TABLE", _agent_cfg.get("audit_log_table", ""))

EPISODIC_MEMORY_TABLE = os.environ.get("EPISODIC_MEMORY_TABLE", _agent_cfg.get("episodic_memory_table", ""))


def _log_notebook_to_audit(notebook_path, notebook_url, size_bytes):
    """Log a saved notebook to the agent_fs_log audit table."""
    def esc(s):
        return s.replace("'", "''") if s else ""

    sql = (
        f"INSERT INTO {AUDIT_LOG_TABLE} "
        f"(operation, path, storage_type, physical_path, size_bytes, status, agent_name) "
        f"VALUES ('save_notebook', '{esc(notebook_path)}', 'workspace', "
        f"'{esc(notebook_url)}', {size_bytes}, 'success', 'orchestrator-agent')"
    )
    _workspace_client.statement_execution.execute_statement(
        warehouse_id=SQL_WAREHOUSE_ID, statement=sql, wait_timeout="30s",
    )


# =============================================================================
# 4b. VariableStore System
# =============================================================================

@dataclass
class StoredVariable:
    """Lightweight metadata wrapper around a retrieved DataFrame."""
    name: str
    df: pd.DataFrame
    source: str = ""
    description: str = ""
    query_sql: str = ""
    metadata: Dict[str, Any] = dc_field(default_factory=dict)
    access_count: int = 0


def _get_df_namespace(config: dict) -> tuple:
    """Derive a per-thread DataFrame namespace tuple from a RunnableConfig."""
    cfg = (config or {}).get("configurable", {})
    user_id = cfg.get("user_id", "default_user")
    thread_id = cfg.get("thread_id", "default_thread")
    return ("dataframes", user_id, thread_id)


# Thread-local storage so concurrent serving requests never share a proxy reference.
import threading as _threading
_tls = _threading.local()


class VariableStore:
    """Thread-scoped proxy wrapping LangGraph BaseStore with a variable_store-compatible API.

    Wraps any LangGraph-compatible BaseStore (InMemoryStore, PostgresStore, etc.)
    and scopes all reads/writes to a per-thread namespace tuple so different
    conversations never see each other's DataFrames.
    """

    def __init__(self, store: Any, config: dict):
        self._store = store
        self._ns = _get_df_namespace(config)

    def _data_dir(self) -> str:
        """Volumes directory for this thread's DataFrames."""
        thread_id = self._ns[-1] if len(self._ns) > 2 else "default"
        email = _get_current_user_email()
        # Volume root is config-driven (_VOLUME_PATH); never hardcode a UC catalog.
        base = globals().get("_VOLUME_PATH", "/Volumes/workspace/hackathon/agent_scratch")
        return f"{base}/data/{email}/{thread_id}"

    def _data_path(self, name: str) -> str:
        """Volumes path for a persisted DataFrame Parquet file."""
        return f"{self._data_dir()}/{name}.parquet"

    def _persist_to_storage(self, name: str, df: pd.DataFrame):
        """Write DataFrame to Volumes as Parquet for durability across restarts."""
        try:
            if _workspace_client is None:
                logger.warning("Cannot persist DataFrame: WorkspaceClient not initialized")
                return
            path = self._data_path(name)
            # Ensure parent directories exist
            dir_path = self._data_dir()
            try:
                _workspace_client.files.create_directory(dir_path)
            except Exception:
                pass  # Already exists
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            buf.seek(0)
            _workspace_client.files.upload(path, buf, overwrite=True)
            logger.info(f"VariableStore PERSISTED: {path} ({len(df)} rows)")
        except Exception as e:
            logger.warning(f"VariableStore persist FAILED for '{name}': {type(e).__name__}: {e}")

    def _load_from_storage(self, name: str) -> Optional[pd.DataFrame]:
        """Load DataFrame from Volumes if not in memory cache."""
        try:
            if _workspace_client is None:
                logger.warning("Cannot load DataFrame: WorkspaceClient not initialized")
                return None
            path = self._data_path(name)
            resp = _workspace_client.files.download(path)
            buf = io.BytesIO(resp.read())
            df = pd.read_parquet(buf)
            logger.info(f"VariableStore LOADED: {path} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.warning(f"VariableStore load FAILED for '{name}': {type(e).__name__}: {e}")
            return None

    @staticmethod
    def _sanitize_df_for_json(df: pd.DataFrame) -> dict:
        """Convert DataFrame to dict, replacing NaN/Inf with None for JSON safety."""
        import numpy as np
        clean = df.where(df.notna() & ~df.isin([np.inf, -np.inf]), other=None)
        return clean.to_dict(orient="list")

    def store(
        self,
        name: str,
        df: pd.DataFrame,
        *,
        source: str = "",
        description: str = "",
        query_sql: str = "",
        metadata: Optional[Dict] = None,
    ) -> str:
        """Persist a DataFrame under ``name`` in memory cache + Volumes."""
        value = {
            "df": self._sanitize_df_for_json(df),
            "columns": list(df.columns),
            "row_count": len(df),
            "source": source,
            "description": description,
            "query_sql": query_sql,
            "metadata": metadata or {},
            "stored_at": time.time(),
            "access_count": 0,
        }
        self._store.put(self._ns, name, value)
        # Persist to Volumes for durability across container restarts
        self._persist_to_storage(name, df)
        cols = list(df.columns)
        preview = ", ".join(cols[:6]) + ("..." if len(cols) > 6 else "")
        return f"Stored '{name}': {df.shape[0]} rows x {df.shape[1]} cols [{preview}]"

    def get(self, name: str) -> Optional[pd.DataFrame]:
        """Return the DataFrame: memory cache first, then Volumes fallback."""
        # Try in-memory cache first
        item = self._store.get(self._ns, name)
        if item is not None:
            return pd.DataFrame(item.value["df"])
        # Fallback: load from Volumes (survives container restarts)
        df = self._load_from_storage(name)
        if df is not None:
            # Re-populate the in-memory cache
            self._store.put(self._ns, name, {
                "df": self._sanitize_df_for_json(df),
                "columns": list(df.columns),
                "row_count": len(df),
                "source": "volumes_restore",
                "description": "Restored from Volumes",
                "stored_at": time.time(),
                "access_count": 0,
            })
        return df

    def get_var(self, name: str) -> Optional[StoredVariable]:
        """Return a StoredVariable (df + metadata) for ``name``, or None."""
        item = self._store.get(self._ns, name)
        if item is None:
            return None
        v = item.value
        return StoredVariable(
            name=name,
            df=pd.DataFrame(v["df"]),
            source=v.get("source", ""),
            description=v.get("description", ""),
            query_sql=v.get("query_sql", ""),
            metadata=v.get("metadata", {}),
            access_count=v.get("access_count", 0),
        )

    def _restore_from_storage(self):
        """Scan Volumes data directory for this thread and restore all Parquet files."""
        try:
            if _workspace_client is None:
                logger.warning("Cannot restore DataFrames: WorkspaceClient not initialized")
                return
            data_dir = self._data_dir()
            logger.info(f"VariableStore RESTORE scanning: {data_dir}")
            try:
                files = list(_workspace_client.files.list_directory_contents(data_dir))
            except Exception as list_err:
                logger.warning(f"VariableStore RESTORE list failed ({type(list_err).__name__}): {list_err}")
                return
            restored = 0
            for f in files:
                file_path = getattr(f, "path", "") or ""
                if not file_path.endswith(".parquet"):
                    continue
                # Extract name from full path
                name = file_path.rsplit("/", 1)[-1].replace(".parquet", "")
                logger.info(f"VariableStore RESTORE attempting: {name} from {file_path}")
                df = self._load_from_storage(name)
                if df is not None:
                    restored += 1
            if restored:
                logger.info(f"VariableStore RESTORED {restored} DataFrames for thread")
            else:
                logger.info(f"VariableStore RESTORE: no .parquet files in {data_dir}")
        except Exception as e:
            logger.warning(f"VariableStore RESTORE scan failed: {type(e).__name__}: {e}")

    def list_all(self) -> List[Dict[str, Any]]:
        """List all DataFrames in the current namespace with summary metadata.

        If the in-memory cache is empty, scan Volumes for persisted Parquet files
        and restore them into the cache.
        """
        items = self._store.search(self._ns)
        # If memory cache is empty, try restoring from Volumes
        if not list(items):
            self._restore_from_storage()
            items = self._store.search(self._ns)
        results = []
        for item in items:
            v = item.value
            cols = v.get("columns", [])
            age_min = round((time.time() - v.get("stored_at", time.time())) / 60, 1)
            df = pd.DataFrame(v["df"])
            results.append(
                {
                    "name": item.key,
                    "rows": v.get("row_count", len(df)),
                    "cols": len(cols),
                    "columns": cols,
                    "dtypes": {c: str(d) for c, d in df.dtypes.items()},
                    "source": v.get("source", ""),
                    "description": v.get("description", ""),
                    "age_min": age_min,
                    "accesses": v.get("access_count", 0),
                }
            )
        return results

    def delete(self, name: str) -> bool:
        """Remove the entry for ``name`` from the store."""
        self._store.delete(self._ns, name)
        return True

    def clear(self):
        """Delete all entries in the current namespace."""
        for item in self._store.search(self._ns):
            self._store.delete(self._ns, item.key)

    @staticmethod
    def auto_name(question: str, space_id: str = "") -> str:
        """Generate a short deterministic variable name from a question string."""
        words = [w.lower() for w in question.split() if len(w) > 2 and w.isalpha()][:3]
        base = "_".join(words) if words else "result"
        suffix = hashlib.md5(f"{question}{space_id}{time.time()}".encode()).hexdigest()[:6]
        return f"{base}_{suffix}"


def inject_store_into_namespace(namespace: dict, proxy: Optional["VariableStore"] = None) -> dict:
    """Add a VariableStore + pandas to an exec() namespace."""
    resolved = proxy or getattr(_tls, "active_proxy", None)
    if resolved is not None:
        namespace["variable_store"] = resolved
    namespace["pd"] = pd
    return namespace


# --- VariableStore LangChain Tools ---

@tool
def store_dataframe(
    name: str,
    columns: list[str],
    rows: list[list],
    description: str = "",
    source: str = "manual",
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """Store tabular data as a named DataFrame in the session variable store.

    Use this to persist transformed data or intermediate computations that
    other tools need to access later. Genie results are auto-stored, so you
    typically only call this for computed/derived data.

    Args:
        name: Unique snake_case name (e.g. "recognition_rate_by_origin", "top_hosts_2024").
        columns: Column name list.
        rows: Data rows as list of lists.
        description: What this data represents.
        source: Origin identifier.

    Returns:
        Confirmation with shape and column preview.
    """
    df = pd.DataFrame(rows, columns=columns)
    return VariableStore(store, config).store(name, df, source=source, description=description)


@tool
def get_dataframe(
    name: str,
    head: int = 20,
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """Retrieve a stored DataFrame by name and return as formatted text.

    Use list_dataframes first to see available variables.

    Args:
        name: Variable name to retrieve.
        head: Max rows to show (default 20, max 50).

    Returns:
        Markdown table with shape info, or error listing available variables.
    """
    proxy = VariableStore(store, config)
    df = proxy.get(name)
    if df is None:
        available = [v["name"] for v in proxy.list_all()]
        return f"Variable '{name}' not found. Available: {available or 'none'}"

    head = min(max(head, 1), 50)
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    row_strs = []
    for _, row in df.head(head).iterrows():
        row_strs.append("| " + " | ".join(
            str(v) if pd.notna(v) else "NULL" for v in row
        ) + " |")

    var = proxy.get_var(name)
    src = var.source if var else ""
    result = f"**{name}** ({df.shape[0]} rows x {df.shape[1]} cols | source: {src})\n\n"
    result += header + "\n" + sep + "\n" + "\n".join(row_strs)
    if len(df) > head:
        result += f"\n... ({len(df) - head} more rows)"
    return result


@tool
def list_dataframes(
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """List all DataFrames in the variable store with metadata.

    Returns:
        Summary of stored variables: name, shape, columns, source, age, accesses.
    """
    variables = VariableStore(store, config).list_all()
    if not variables:
        return (
            "Variable store is empty. Data is auto-stored from Genie queries, "
            "or use store_dataframe to add data manually."
        )
    lines = ["**Variable Store:**\n"]
    for v in variables:
        cols = ", ".join(v["columns"][:5])
        if len(v["columns"]) > 5:
            cols += f"... +{len(v['columns']) - 5} more"
        lines.append(
            f"- `{v['name']}` -- {v['rows']}x{v['cols']} | [{cols}] | "
            f"src: {v.get('source', '')} | {v.get('age_min', '?')}m old | {v.get('accesses', 0)} reads"
        )
    return "\n".join(lines)


# --- VariableStore Preamble & Writeback for Remote Execution ---

_VS_SENTINEL = "__VS_STORE__:"


def _build_variable_store_preamble(proxy: "LakebaseVariableStore") -> str:
    """Build a preamble that reads/writes DataFrames via Lakebase Postgres.

    Generates code that:
    1. Connects to Lakebase using psycopg (installed on serverless >=Env 2)
    2. Reads DataFrames from real Postgres tables (same tables the agent wrote)
    3. Writes back via the __VS_STORE__ sentinel (parsed by orchestrator)

    This makes notebooks self-contained and **re-runnable manually** —
    the Lakebase host, schema, user_id and thread_id are baked in.
    Credentials are retrieved from a Databricks secret scope at runtime.
    """
    from urllib.parse import urlparse

    # Get the Lakebase URL from the environment (same one the agent uses)
    lakebase_url = os.environ.get(
        "LAKEBASE_URL",
        (_CFG.get("lakebase", {}) or {}).get("url", ""),
    )
    schema = proxy._schema
    user_id = proxy._user_id
    thread_id = proxy._thread_id

    # Parse URL to separate credentials from connection details
    parsed = urlparse(lakebase_url)
    lakebase_host = parsed.hostname or ""
    lakebase_port = parsed.port or 5432
    lakebase_db = (parsed.path or "/").lstrip("/")
    lakebase_params = parsed.query or ""
    url_params_suffix = f"?{lakebase_params}" if lakebase_params else ""

    # Secret scope config — defaults match the CLI setup instructions
    secrets_cfg = _CFG.get("secrets", {}) or {}
    secret_scope = secrets_cfg.get("scope_name", "agent-secrets")
    username_key = secrets_cfg.get("lakebase_username_key", "lakebase-username")
    password_key = secrets_cfg.get("lakebase_password_key", "lakebase-password")

    # Build cell separators dynamically to avoid the Databricks notebook
    # parser splitting the f-string across cells.
    _CMD_SEP = "# " + "COMMAND " + "----------"
    _PIP_CELL = '# ' + 'MAGIC %pip install -q "psycopg[binary]"'

    return f'''\
{_PIP_CELL}

{_CMD_SEP}

# -- variable_store preamble (auto-injected by Orchestrator Agent) --
# DataFrames backed by Lakebase Postgres tables (v2 — self-contained).
# Re-run this notebook manually and the variable_store will reconnect.
# Credentials retrieved from Databricks secret scope at runtime.
import pandas as pd
import json
import hashlib
import math

_VS_LAKEBASE_USER = dbutils.secrets.get(scope={json.dumps(secret_scope)}, key={json.dumps(username_key)})
_VS_LAKEBASE_PASS = dbutils.secrets.get(scope={json.dumps(secret_scope)}, key={json.dumps(password_key)})
_VS_LAKEBASE_URL = f"postgresql://{{_VS_LAKEBASE_USER}}:{{_VS_LAKEBASE_PASS}}@{lakebase_host}:{lakebase_port}/{lakebase_db}{url_params_suffix}"
_VS_SCHEMA = {json.dumps(schema)}
_VS_USER_ID = {json.dumps(user_id)}
_VS_THREAD_ID = {json.dumps(thread_id)}

class _RemoteVarStore:
    """Lightweight variable_store stub backed by Lakebase Postgres.
    Reads/writes DataFrames as real Postgres tables — same layout the
    orchestrator's LakebaseVariableStore uses.
    """
    def __init__(self, lakebase_url, schema, user_id, thread_id):
        self._url = lakebase_url
        self._schema = schema
        self._user_id = user_id
        self._thread_id = thread_id
        self._cache = {{}}
        self._conn = None

    def _get_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg
            self._conn = psycopg.connect(self._url, autocommit=True)
        return self._conn

    @staticmethod
    def _table_name(user_id, thread_id, name):
        h = hashlib.sha1(f"{{user_id}}::{{thread_id}}::{{name}}".encode()).hexdigest()[:12]
        return f"variable_store_{{h}}"

    def _qi(self, name):
        return '"' + str(name).replace('"', '""') + '"'

    def _full_table(self, name):
        t = self._table_name(self._user_id, self._thread_id, name)
        return f"{{self._qi(self._schema)}}.{{self._qi(t)}}"

    def _index_table(self):
        return f"{{self._qi(self._schema)}}.{{self._qi('variable_store_index')}}"

    def get(self, name):
        if name in self._cache:
            return self._cache[name]
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT table_name FROM {{self._index_table()}} "
                    f"WHERE user_id = %s AND thread_id = %s AND name = %s",
                    (self._user_id, self._thread_id, name),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(f"SELECT * FROM {{self._qi(self._schema)}}.{{self._qi(row[0])}}")
                data = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
            df = pd.DataFrame(data, columns=cols)
            self._cache[name] = df
            return df
        except Exception as e:
            print(f"Warning: could not load '{{name}}' from Lakebase: {{e}}")
            return None

    def list_all(self):
        results = []
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT name, row_count, schema_json FROM {{self._index_table()}} "
                    f"WHERE user_id = %s AND thread_id = %s ORDER BY created_at DESC",
                    (self._user_id, self._thread_id),
                )
                for name, row_count, schema_json in cur.fetchall():
                    cols = []
                    try:
                        cols = [s["name"] for s in json.loads(schema_json or "[]")]
                    except Exception:
                        pass
                    results.append({{"name": name, "rows": row_count or 0, "columns": cols}})
        except Exception as e:
            print(f"Warning: list_all failed: {{e}}")
        return results

    def store(self, name, df, *, source="", description="", query_sql="", metadata=None):
        # Convert Spark DataFrame to pandas if needed
        if hasattr(df, 'toPandas'):
            df = df.toPandas()
        # Sanitize NaN/Inf for JSON safety
        import numpy as np
        clean = df.where(df.notna() & ~df.isin([np.inf, -np.inf]), other=None)
        payload = json.dumps({{
            "name": name,
            "df": clean.to_dict(orient="list"),
            "columns": list(df.columns),
            "row_count": len(df),
            "source": source,
            "description": description,
            "query_sql": query_sql,
        }}, default=str)
        print(f"{_VS_SENTINEL}{{payload}}")
        self._cache[name] = df
        return f"Stored '{{name}}': {{df.shape[0]}} rows x {{df.shape[1]}} cols"

variable_store = _RemoteVarStore(_VS_LAKEBASE_URL, _VS_SCHEMA, _VS_USER_ID, _VS_THREAD_ID)
# -- end preamble --

{_CMD_SEP}

'''


def _parse_and_commit_writebacks(output: str, proxy: "VariableStore") -> tuple[str, list[str]]:
    """Scan execution output for sentinel lines, commit them to the real store."""
    clean_lines = []
    stored_names = []
    for line in output.splitlines():
        if line.startswith(_VS_SENTINEL):
            try:
                payload = json.loads(line[len(_VS_SENTINEL):])
                df = pd.DataFrame(payload["df"])
                proxy.store(
                    payload["name"],
                    df,
                    source=payload.get("source", "notebook"),
                    description=payload.get("description", ""),
                    query_sql=payload.get("query_sql", ""),
                )
                stored_names.append(payload["name"])
            except Exception:
                clean_lines.append(line)
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines), stored_names


# =============================================================================
# 4c. ask_genie_space (with auto-store)
# =============================================================================

def _format_genie_response(
    question: str, genie_message: Any, space_id: str
) -> Dict[str, Any]:
    """Format a Genie SDK response into a clean dictionary."""
    result: Dict[str, Any] = {
        "question": question,
        "conversation_id": genie_message.conversation_id,
        "message_id": genie_message.id,
        "status": str(genie_message.status.value) if genie_message.status else "UNKNOWN",
    }

    if genie_message.attachments:
        for attachment in genie_message.attachments:
            if attachment.query:
                result["sql"] = attachment.query.query or ""
                result["description"] = attachment.query.description or ""

                if attachment.query.query_result_metadata:
                    result["row_count"] = attachment.query.query_result_metadata.row_count

                if attachment.attachment_id:
                    try:
                        data_result = _workspace_client.genie.get_message_query_result_by_attachment(
                            space_id=space_id,
                            conversation_id=genie_message.conversation_id,
                            message_id=genie_message.id,
                            attachment_id=attachment.attachment_id,
                        )
                        if data_result.statement_response:
                            sr = data_result.statement_response
                            if sr.manifest and sr.manifest.schema and sr.manifest.schema.columns:
                                result["columns"] = [c.name for c in sr.manifest.schema.columns]
                            if sr.result and sr.result.data_array:
                                result["data"] = sr.result.data_array
                    except Exception as e:
                        logger.warning(f"Failed to fetch Genie query results: {e}")

            if attachment.text:
                result["text_response"] = attachment.text.content or ""

    return result


@tool
def ask_genie_space(
    space_id: str,
    question: str,
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """Ask a natural language question to a Genie Space and get the answer.

    This is the primary data retrieval tool. Genie generates SQL from your
    question, executes it against Unity Catalog, and returns the results.

    IMPORTANT: Every call starts a NEW conversation (stateless). Do NOT try
    to pass conversation_id for follow-ups -- reformulate the full question
    each time so Genie has complete context.

    How to determine which space to use:
    - Read the skill overviews (auto-injected into the system prompt) to find
      the matching Genie Space based on routing keywords and table coverage.
    - Each skill lists its Space ID, tables, and the types of questions it covers.

    Args:
        space_id: The Genie Space ID to query. Get this from the matching
                  skill overview based on the question's domain.
        question: A clear, specific natural language question.

    Returns:
        Formatted string with SQL, description, data, row count,
        and variable store name (if auto-stored).
    """
    if not space_id:
        return "Error: space_id is required. Check the skill overviews for available Genie Space IDs."

    try:
        genie_message = _workspace_client.genie.start_conversation_and_wait(
            space_id=space_id,
            content=question,
            timeout=timedelta(seconds=GENIE_TIMEOUT_SECONDS),
        )

        response = _format_genie_response(question, genie_message, space_id)

        # Auto-store result in variable store (if store is injected)
        _var_name = None
        if store is not None:
            try:
                _cols = response.get("columns")
                _data = response.get("data")
                if _cols and _data:
                    _proxy = VariableStore(store, config or {})
                    _df = pd.DataFrame(_data, columns=_cols)
                    _var_name = VariableStore.auto_name(question, space_id)
                    _proxy.store(
                        _var_name, _df,
                        source=f"genie:{space_id}",
                        description=question,
                        query_sql=response.get("sql", ""),
                    )
            except Exception:
                _var_name = None

        parts = []
        status = response.get("status", "UNKNOWN")
        parts.append(f"Status: {status}")

        if response.get("description"):
            parts.append(f"Interpretation: {response['description']}")

        if response.get("sql"):
            parts.append(f"SQL:\n```sql\n{response['sql']}\n```")

        if response.get("columns") and response.get("data"):
            columns = response["columns"]
            data = response["data"]
            row_count = response.get("row_count", len(data))
            parts.append(f"Results ({row_count} rows):")

            header = "| " + " | ".join(str(c) for c in columns) + " |"
            separator = "| " + " | ".join("---" for _ in columns) + " |"
            parts.append(header)
            parts.append(separator)

            display_limit = 50
            for row in data[:display_limit]:
                row_str = "| " + " | ".join(
                    str(v) if v is not None else "NULL" for v in row
                ) + " |"
                parts.append(row_str)

            if len(data) > display_limit:
                parts.append(f"... ({len(data) - display_limit} more rows truncated)")
        elif response.get("row_count") is not None:
            parts.append(f"Row count: {response['row_count']}")

        if response.get("text_response"):
            parts.append(f"Genie summary: {response['text_response']}")

        if status not in ("COMPLETED", "EXECUTING_QUERY"):
            error = response.get("error", "Genie did not complete successfully")
            parts.append(f"Error: {error}")

        if _var_name:
            parts.append(f"\nData stored as variable: `{_var_name}`")

        return "\n".join(parts)

    except TimeoutError:
        return (
            f"Error: Genie response timed out after {GENIE_TIMEOUT_SECONDS}s. "
            f"The question may be too complex. Try simplifying or breaking it into parts."
        )
    except Exception as e:
        return f"Error querying Genie Space: {e}"


# =============================================================================
# 4d. run_spark_sql
# =============================================================================

@tool
def run_spark_sql(
    sql: str,
    max_rows: int = 100,
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """Execute a Spark SQL query on the Databricks SQL warehouse and return results.

    Runs SQL directly via the Statement Execution API -- no cluster needed.
    Results are automatically stored in the VariableStore for downstream use.

    Args:
        sql: A complete SQL SELECT statement. All tables should be fully qualified.
        max_rows: Maximum rows to return. Default 100.

    Returns:
        Formatted results with column headers and data rows, or error details.
    """
    if not sql.strip():
        return "Error: Empty SQL statement."

    if _workspace_client is None:
        return "Error: workspace client not initialized."

    wh_err = _ensure_warehouse_running(_workspace_client, SQL_WAREHOUSE_ID)
    if wh_err:
        return f"SQL warehouse not available: {wh_err}"

    try:
        response = _workspace_client.statement_execution.execute_statement(
            warehouse_id=SQL_WAREHOUSE_ID,
            statement=sql,
            wait_timeout="50s",
        )

        status = response.status
        if status.state.value == "FAILED":
            error_msg = status.error.message if status.error else "Unknown error"
            return f"SQL execution failed:\n{error_msg}\n\nSQL:\n{sql}"

        if status.state.value != "SUCCEEDED":
            return f"SQL status: {status.state.value}. Try simplifying the query."

        manifest = response.manifest
        result = response.result

        if not manifest or not result:
            return "Query succeeded but returned no results."

        columns = [col.name for col in manifest.schema.columns] if manifest.schema and manifest.schema.columns else []
        data = result.data_array or []

        if not columns:
            return "Query succeeded but returned no columns."
        if not data:
            return f"Query succeeded, 0 rows.\nColumns: {', '.join(columns)}"

        parts = [f"Results ({len(data)} rows):"]
        parts.append("")
        parts.append("| " + " | ".join(str(c) for c in columns) + " |")
        parts.append("| " + " | ".join("---" for _ in columns) + " |")

        for row in data[:max_rows]:
            parts.append("| " + " | ".join(str(v) if v is not None else "NULL" for v in row) + " |")

        if len(data) > max_rows:
            parts.append(f"... ({len(data) - max_rows} more rows)")

        parts.append("")
        parts.append("JSON (first 10 rows):")
        parts.append(json.dumps([dict(zip(columns, row)) for row in data[:10]], indent=2, default=str))

        # Auto-store results in VariableStore (mirrors ask_genie_space pattern)
        _var_name = None
        if store is not None and columns and data:
            try:
                _proxy = VariableStore(store, config or {})
                _df = pd.DataFrame(data, columns=columns)
                _var_name = VariableStore.auto_name(sql[:60], "spark_sql")
                _proxy.store(_var_name, _df, source="spark_sql", query_sql=sql[:500])
            except Exception as e:
                logger.warning(f"run_spark_sql auto-store failed: {e}")
                _var_name = None
        if _var_name:
            parts.append(f"\nData stored as variable: `{_var_name}`")

        return "\n".join(parts)

    except Exception as e:
        return f"Statement Execution API error: {e}\n\nSQL:\n{sql}"


# =============================================================================
# 4e. run_python_notebook (merged: serverless + VariableStore preamble)
# =============================================================================

def _save_notebook_to_workspace(code, name, description):
    """Save code as a Databricks notebook and return (notebook_path, notebook_url).

    Write strategy: OBO first, SP fallback.

    The user is ``CAN_MANAGE`` on their own ``/Workspace/Users/<email>/`` —
    they can mkdirs + upload there if their forwarded token carries the
    Workspace API scopes (``workspace.workspace`` is the only Apps-issuable
    scope that maps; see the OBO workspace-scope mapping note / wiki guide
    the stabilisation notes for the historical scope-claim issue).
    OBO upload was broken in 2026-04 because ``workspace.workspace`` did
    not satisfy the IMPORT API's ``workspace`` claim; we still try OBO
    first because (a) Databricks may have fixed the mapping, (b) when it
    works the audit trail attributes the write to the user, and (c) it
    avoids the SP needing admin-level perms on every user's home dir.

    SP fallback: the OAuth-M2M SP (``ce261965-…``) only sits in
    ``grp_go_gdp_mgmt`` — NOT the workspace ``admins`` group — so it has
    no permission on ``/Workspace/Users/<other-user>/``. Workspace API
    returns 404 ``ResourceDoesNotExist`` (security-through-obscurity for
    perms-denied), which is what surfaced as the 2026-05-07 regression.
    The fallback path will keep failing until either the SP is added to
    the ``admins`` group or per-user CAN_MANAGE grants are made.

    All failures are surfaced at WARNING so they appear in the Logs API
    (see the Model Serving warning-level-logs note).
    """
    _user_client = _user_workspace_client()
    _have_obo = _user_client is not _workspace_client and _user_client is not None
    try:
        _current_user = (
            _user_client.current_user.me().user_name if _have_obo
            else _workspace_client.current_user.me().user_name
        )
    except Exception:
        _current_user = _workspace_client.current_user.me().user_name
    output_dir = f"/Workspace/Users/{_current_user}/agent_generated"
    notebook_content = (
        "# Databricks notebook source\n"
        "# MAGIC %md\n"
        f"# MAGIC ## {description}\n"
        "# MAGIC\n"
        f"# MAGIC *Generated by Orchestrator Agent on {current_date}*\n"
        "\n# COMMAND ----------\n\n"
        f"{code}\n"
    )
    notebook_path = f"{output_dir}/{name}"

    def _try_write(client, label):
        try:
            client.workspace.mkdirs(output_dir)
        except Exception as e:
            logger.warning(
                f"[v3-debug:notebook-save] mkdirs FAILED via={label} dir={output_dir} "
                f"err={type(e).__name__}: {e}"
            )
            # mkdirs failures often co-occur with upload failures, but try
            # upload anyway — Workspace API returns 404 for both
            # missing-dir and perms-denied, and idempotent mkdirs may
            # have succeeded against a directory we can't read back.
        try:
            client.workspace.upload(
                notebook_path, io.BytesIO(notebook_content.encode("utf-8")),
                format=ImportFormat.SOURCE, language=Language.PYTHON, overwrite=True,
            )
            obj = client.workspace.get_status(notebook_path)
            return obj, None
        except Exception as e:
            logger.warning(
                f"[v3-debug:notebook-save] upload FAILED via={label} path={notebook_path} "
                f"err={type(e).__name__}: {e}"
            )
            return None, e

    obj, last_err = (None, None)
    via = None
    if _have_obo:
        obj, last_err = _try_write(_user_client, "obo")
        if obj is not None:
            via = "obo"
    if obj is None:
        obj, last_err = _try_write(_workspace_client, "sp")
        if obj is not None:
            via = "sp"

    if obj is None:
        logger.warning(
            f"[v3-debug:notebook-save] FAILED path={notebook_path} "
            f"err={type(last_err).__name__}: {last_err}"
        )
        return notebook_path, f"(save failed: {last_err})"

    # Modern editor URL with ?o=<workspace_id> so Databricks resolves the
    # correct workspace context. The legacy `/#notebook/<id>` form invited
    # LLMs to rewrite it into the modern pattern and fabricate the ?o=
    # value from training data. We emit the canonical URL now.
    if WORKSPACE_ID:
        notebook_url = f"{WORKSPACE_URL}/editor/notebooks/{obj.object_id}?o={WORKSPACE_ID}"
    else:
        notebook_url = f"{WORKSPACE_URL}/editor/notebooks/{obj.object_id}"
    try:
        _log_notebook_to_audit(notebook_path, notebook_url, len(notebook_content))
    except Exception as log_err:
        logger.warning(f"Failed to log notebook to audit: {log_err}")
    logger.warning(
        f"[v3-debug:notebook-save] OK via={via} path={notebook_path} url={notebook_url} "
        f"object_id={obj.object_id} workspace_id={WORKSPACE_ID or 'unknown'}"
    )
    return notebook_path, notebook_url


def _execute_serverless(notebook_path, timeout_seconds=600):
    """Execute a saved notebook via serverless Jobs API (runs/submit).

    Uses the OBO client when available so the serverless run executes
    under the calling user's identity — UC grants on the user determine
    what data the notebook can access. Falls back to SP if OBO is
    unavailable.
    """
    from databricks.sdk.service.jobs import (
        SubmitTask,
        NotebookTask,
        Source,
    )
    _user_client = _user_workspace_client()

    try:
        submit_response = _user_client.jobs.submit(
            run_name=f"agent-exec-{notebook_path.split('/')[-1]}",
            tasks=[
                SubmitTask(
                    task_key="agent_run",
                    notebook_task=NotebookTask(
                        notebook_path=notebook_path,
                        source=Source.WORKSPACE,
                    ),
                )
            ],
        )
        run_id = submit_response.response.run_id if hasattr(submit_response, "response") else submit_response.run_id

        logger.info(f"Serverless run submitted: run_id={run_id}")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            run = _user_client.jobs.get_run(run_id)
            state = run.state
            life_cycle = str(state.life_cycle_state) if state else "UNKNOWN"

            if "TERMINATED" in life_cycle or "INTERNAL_ERROR" in life_cycle or "SKIPPED" in life_cycle:
                result_state = str(state.result_state) if state.result_state else "UNKNOWN"

                if result_state == "SUCCESS" or "SUCCESS" in result_state:
                    try:
                        if run.tasks:
                            task_run_id = run.tasks[0].run_id
                            output = _user_client.jobs.get_run_output(task_run_id)
                        else:
                            output = _user_client.jobs.get_run_output(run_id)
                        if output.notebook_output and output.notebook_output.result:
                            return output.notebook_output.result
                        return "Code executed successfully (no output). Use dbutils.notebook.exit('result') to return output."
                    except Exception as out_err:
                        logger.warning(f"Could not capture output: {out_err}")
                        return "Code executed successfully (no output captured)."
                else:
                    error_msg = state.state_message if state.state_message else "Unknown error"
                    return f"Execution failed ({result_state}): {error_msg}"

            time.sleep(5)

        return f"Execution timed out after {timeout_seconds}s (run_id={run_id}). Check run status in Databricks."

    except Exception as e:
        logger.exception("Serverless execution failed")
        return f"Serverless execution error: {e}"


def _execute_on_cluster(code, timeout_seconds=180):
    """Execute code on the all-purpose cluster via CommandExecution API."""
    cluster_err = _ensure_cluster_running(_workspace_client, CLUSTER_ID)
    if cluster_err:
        return f"Error: {cluster_err}"

    try:
        ctx = _workspace_client.command_execution.create(
            cluster_id=CLUSTER_ID, language=ComputeLanguage.PYTHON,
        ).result(timeout=timedelta(seconds=120))
        try:
            result = _workspace_client.command_execution.execute(
                cluster_id=CLUSTER_ID, context_id=ctx.id,
                language=ComputeLanguage.PYTHON, command=code,
            ).result(timeout=timedelta(seconds=timeout_seconds))
            if result.results:
                if result.results.result_type and str(result.results.result_type) == "error":
                    return f"Execution error:\n{result.results.cause or 'Unknown error'}"
                return result.results.data or "Code executed successfully (no output)."
            return "Code executed successfully (no output)."
        finally:
            _workspace_client.command_execution.destroy(cluster_id=CLUSTER_ID, context_id=ctx.id)
    except Exception as e:
        logger.exception("CommandExecution failed")
        return f"CommandExecution failed ({type(e).__name__}): {e}"


USE_SERVERLESS = str(os.environ.get(
    "USE_SERVERLESS_EXECUTION", _compute_cfg.get("use_serverless_execution", ""),
)).lower() == "true"


@tool
def run_python_notebook(
    code: str, name: str, description: str = "Agent-generated analysis",
    save_notebook: bool = True,
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """Execute PySpark/Python code and optionally save as a Databricks notebook.

    Use when you need spark.sql() with dataframe operations, pandas processing,
    or code that goes beyond a single SQL SELECT.

    For simple SQL queries, prefer run_spark_sql -- it's faster.

    Execution: Runs on serverless compute by default (no cluster startup needed).
    Falls back to cluster if serverless is unavailable.

    A ``variable_store`` object is automatically available in the code context
    with methods: ``.get(name)``, ``.store(name, df)``, ``.list_all()``.

    **Important:** To capture output from serverless execution, end your code with:
        dbutils.notebook.exit("your result string here")
    Regular print() output may not be captured in serverless mode.

    Args:
        code: Complete Python code to execute. Has access to spark, pandas, numpy.
        name: Short name for the notebook.
        description: Brief description.
        save_notebook: If True, save as a Databricks notebook.

    Returns:
        Execution output + notebook link (if saved).
    """
    if _workspace_client is None:
        return "Error: workspace client not initialized."

    # Build VariableStore preamble if store is available
    proxy = VariableStore(store, config) if store is not None else None
    preamble = _build_variable_store_preamble(proxy) if proxy else ""
    full_code = preamble + code

    # Save notebook WITH preamble so users can re-run it independently.
    # The preamble contains the Volumes paths for all stored DataFrames
    # plus a self-healing directory scan — making the notebook self-contained.
    notebook_path, notebook_url = None, None
    if save_notebook:
        notebook_path, notebook_url = _save_notebook_to_workspace(full_code, name, description)

    # Execute
    if USE_SERVERLESS and notebook_path and "(save failed" not in str(notebook_url):
        exec_output = _execute_serverless(notebook_path)
    else:
        exec_output = _execute_on_cluster(full_code, timeout_seconds=180)

    # Parse VariableStore writebacks from execution output
    if proxy and _VS_SENTINEL in str(exec_output):
        exec_output, stored_names = _parse_and_commit_writebacks(str(exec_output), proxy)
        if stored_names:
            exec_output += f"\n\nStored to variable store: {', '.join(stored_names)}"

    # Build response
    parts = [f"Execution output:\n{exec_output}"]
    if notebook_url and "(save failed" not in str(notebook_url):
        parts.append(f"\nNotebook: {notebook_url}")

    return "\n".join(parts)


# =============================================================================
# 4f. run_python_code (fast in-process exec)
# =============================================================================

@tool
def run_python_code(
    code: str,
    config: RunnableConfig = None,
    store: Annotated[Any, InjectedStore()] = None,
) -> str:
    """Execute Python code instantly in the current process.

    Use for quick analysis, calculations, and data transformations.
    Full access to pandas, plotly, numpy, json, os, and all installed packages.
    Use print() to produce output.

    A ``variable_store`` object is automatically available with methods:
    ``.get(name)``, ``.store(name, df)``, ``.list_all()``.

    Args:
        code: Complete, self-contained Python code to execute.

    Returns:
        Captured stdout output, or error details.
    """
    _proxy = VariableStore(store, config) if store is not None else None
    if _proxy is not None:
        _tls.active_proxy = _proxy
    namespace = {"__builtins__": __builtins__}
    inject_store_into_namespace(namespace, _proxy)
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            exec(code, namespace)
        output = stdout_capture.getvalue()
        stderr_out = stderr_capture.getvalue()
        if stderr_out.strip():
            stderr_lines = [
                l for l in stderr_out.splitlines()
                if "DeprecationWarning" not in l and "UserWarning" not in l
            ]
            if stderr_lines:
                output = f"{output}\n[stderr]: {chr(10).join(stderr_lines)}" if output else chr(10).join(stderr_lines)
        return output.strip() if output.strip() else "Code executed successfully (no output)."
    except Exception as e:
        partial = stdout_capture.getvalue()
        error_msg = f"{type(e).__name__}: {e}"
        return f"{partial}\n\nExecution error:\n{error_msg}" if partial else f"Execution error:\n{error_msg}"


# =============================================================================
# 4g. render_chart — replaced by tools/render_chart.py (B1 + F1)
# =============================================================================
# The v1 render_visualization function, CHART_TYPES, _choose_chart_type,
# _PLOTLY_BAR/HBAR/LINE/PIE/SCATTER, and _PLOTLY_BODIES have been deleted.
# Chart rendering now uses the editorial theme helpers and writes HTML to Volumes.
# See tools/render_chart.py for the replacement.
CHART_TYPES_REMOVED_PLACEHOLDER = True  # Marker for grep — remove after B7 test migration

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 5: System Prompts
# MAGIC
# MAGIC Prompt templates + factory functions live in this package's
# MAGIC ``subagents/prompts.py``.
# MAGIC This cell binds runtime values (``current_date``, ``volume_path``,
# MAGIC ``scratch_schema``, ``skill_tables_text``) and assigns the three prompt
# MAGIC strings used by Cell 7's ``create_production_agent``.

# COMMAND ----------

# --- Ensure this package is importable so we can load subagents/ ---
# Mirrors the sys.path shim used for backend.py in Cell 6. __file__ is
# available when the notebook is imported as a Python module (e.g. MLflow
# log_model), and is None when run interactively — in which case the
# workspace client's CWD fallback is used.
_file_path_for_subagents = globals().get("__file__")
_subagents_imported = False
if _file_path_for_subagents:
    _this_dir_sa = Path(_file_path_for_subagents).parent
    for _candidate_sa in [_this_dir_sa, _this_dir_sa / "code", _this_dir_sa.parent]:
        if (_candidate_sa / "subagents" / "__init__.py").exists():
            if str(_candidate_sa) not in sys.path:
                sys.path.insert(0, str(_candidate_sa))
            _subagents_imported = True
            break

if not _subagents_imported:
    _cwd_sa = Path.cwd()
    for _candidate_sa in [_cwd_sa, _cwd_sa.parent]:
        if (_candidate_sa / "subagents" / "__init__.py").exists():
            if str(_candidate_sa) not in sys.path:
                sys.path.insert(0, str(_candidate_sa))
            break

from subagents import (
    build_orchestrator_prompt,
    build_python_analyst_prompt,
    build_data_viz_prompt,
)

# --- tool + variable store + middleware imports ---
# The sys.path shim above already covers tools/, variable_store/, and
# middleware/ — they're siblings of subagents/ in this package.
from variable_store import LakebaseVariableStore
from tools.think_tool import think_tool
from tools.ask_genie_space import build_ask_genie_space_tool
from tools.run_spark_sql import build_run_spark_sql_tool
from util.trace_collector import drain as _drain_tool_queries, start_trace as _start_trace
# Episodic memory dropped for hackathon — see decisions doc 2026-05-13.
# Inert stubs so any leftover call sites compile + no-op.
def recall_past_analysis(*args, **kwargs):
    return None
def format_episodic_context(*args, **kwargs):
    return ""
def log_to_episodic_memory(*args, **kwargs):
    return None
from tools.describe_dataframe import build_describe_dataframe_tool
from tools.query_stored_dfs import build_query_stored_dfs_tool
from tools.save_python_notebook import build_save_python_notebook_tool
from tools.run_python_notebook import build_run_python_notebook_tool as build_run_python_notebook_tool_v2
from tools.compose_infographic import build_compose_infographic_tool
from tools.compose_story import build_compose_story_tool
from tools.compose_document import build_compose_document_tool
from tools.compose_deck import build_compose_deck_tool
# Neo4j skills-brain retrieval — the ONE swap vs. the production orchestrator.
# Replaces DeepAgents' filesystem skill retrieval (auto-injected SKILL.md
# overviews + a read_file walk over /skills/) with a single graph query.
from tools.find_skill import build_find_skill_tool

# Langmem hot-path user preferences. The tool writes to the LangGraph
# PostgresStore that's already wired for episodic memory; namespace is
# substituted from `config["configurable"]["langgraph_user_id"]` at
# tool-invocation time so writes are scoped per OBO-resolved user. Reads
# happen separately via _retrieve_user_prefs() in predict_stream — the
# agent doesn't get a search tool. See the user-preferences memory pattern.
try:
    from langmem import create_manage_memory_tool
    save_user_preference = create_manage_memory_tool(
        namespace=("user_prefs", "{langgraph_user_id}"),
        name="save_user_preference",
        instructions=(
            "Save durable user preferences only — visualization style, default "
            "region or division, preferred terminology, response-length tone. "
            "NEVER save numeric findings, query results, KPIs, or any per-period "
            "values. If the user asks to remember an actual data point, decline "
            "and explain that prefs are for style guidance, not facts."
        ),
    )
    logger.warning(
        f"[user-prefs:init] save_user_preference tool created. "
        f"name={getattr(save_user_preference, 'name', 'N/A')!r} "
        f"type={type(save_user_preference).__name__}"
    )
except Exception as _langmem_err:
    save_user_preference = None
    logger.warning(f"[user-prefs:init] langmem unavailable, save_user_preference disabled: {_langmem_err}")


def _retrieve_user_prefs(store, user_id: str, query: str, limit: int = 3) -> str:
    """Search the per-user prefs namespace and format as a markdown block.

    Returns "" if the store is unset, the namespace is empty, or the search
    fails — never raises into the request path. The block is style-guidance
    only; the orchestrator prompt's "User Preferences" section forbids
    quoting it as a factual finding.
    """
    if store is None or not user_id or user_id == "default_user":
        return ""
    try:
        items = store.search(("user_prefs", user_id), query=query, limit=limit)
    except Exception as e:
        logger.warning(f"[user-prefs] search failed (skipping): {e}")
        return ""
    if not items:
        return ""
    lines = ["## User Preferences (style guidance only — never quote as facts)"]
    for item in items:
        val = getattr(item, "value", {}) or {}
        content = val.get("content") if isinstance(val, dict) else None
        if not content:
            content = str(val)
        lines.append(f"- {content}")
    return "\n".join(lines)

# Override the v1 VariableStore class (Cell 4) with the Postgres-native v2.
# All v1 inline tools (store_dataframe, list_dataframes, render_visualization)
# reference VariableStore by bare name — this alias makes them use the
# LakebaseVariableStore transparently. The v1 class in Cell 4 becomes dead
# code, kept only to avoid deleting 200 lines mid-refactor.
VariableStore = LakebaseVariableStore  # type: ignore[misc]

# Middleware: import v2 allow-list if deepagents_framework is available
# (production / Databricks). Falls back to Cell 3 inline definitions
# (v1 allow-list) if running locally where deepagents isn't installed.
try:
    from middleware.tool_filter import (
        ModelServingToolFilterMiddleware,
        FailedToolPruningMiddleware,
    )
except ImportError:
    pass  # Cell 3 definitions remain in scope as fallback

# Module-level global for DuckDB-postgres DSN — set in _init_checkpointer
_DUCKDB_LAKEBASE_DSN = ""

# Volume path + scratch schema are config-driven; the fallbacks below are
# neutral placeholders — never hardcode a real UC catalog.
_VOLUME_PATH = _CFG.get("agent", {}).get(
    "volume_path", "/Volumes/workspace/hackathon/agent_scratch"
)
_SCRATCH_SCHEMA = _CFG.get("agent", {}).get("scratch_schema", "workspace.hackathon")

ORCHESTRATOR_PROMPT = build_orchestrator_prompt(
    current_date=current_date,
    volume_path=_VOLUME_PATH,
    scratch_schema=_SCRATCH_SCHEMA,
    skill_tables_text=_SKILL_TABLES_TEXT,
)

PYTHON_ANALYST_PROMPT = build_python_analyst_prompt(
    current_date=current_date,
    volume_path=_VOLUME_PATH,
    scratch_schema=_SCRATCH_SCHEMA,
)

DATA_VIZ_PROMPT = build_data_viz_prompt(current_date=current_date)

_ORIGINAL_CELL5_PROMPT_BODIES_EXTERNALIZED = True  # prompt bodies now in subagents/prompts.py

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 6: Backend Factory

# COMMAND ----------

# --- Import DatabricksVolumesBackend ---
# NOTE: the Volumes backend module is `backend.py` in this package; the module
# name is `backend` accordingly.
_file_path_for_backend = globals().get("__file__")
_backend_imported = False
if _file_path_for_backend:
    _this_dir = Path(_file_path_for_backend).parent
    for _candidate in [_this_dir, _this_dir / "code", _this_dir.parent]:
        _backend_file = _candidate / "backend.py"
        if _backend_file.exists():
            if str(_candidate) not in sys.path:
                sys.path.insert(0, str(_candidate))
            _backend_imported = True
            break

if not _backend_imported:
    _cwd = Path.cwd()
    for _candidate in [_cwd, _cwd.parent]:
        _backend_file = _candidate / "backend.py"
        if _backend_file.exists():
            if str(_candidate) not in sys.path:
                sys.path.insert(0, str(_candidate))
            break

from backend import DatabricksVolumesBackend


def create_backend(runtime):
    """Backend factory: DatabricksVolumesBackend for file ops.

    NOTE (neo4j fork): the ``/skills/`` FilesystemBackend route is REMOVED.
    The agent no longer reads skill files at all — the Neo4j knowledge graph
    (find_skill) is the sole knowledge source. The ``skills/`` directory still
    ships in code_paths because the compose_deck / compose_infographic TOOLS
    load runtime ASSETS from it (ra_template.pptx, html scaffolds, fonts) via a
    direct filesystem path — that's a tool-internal read, not an agent read,
    so it's unaffected by dropping this route.
    """
    return CompositeBackend(
        default=DatabricksVolumesBackend(
            workspace_client=_workspace_client,
            sql_warehouse_id=SQL_WAREHOUSE_ID,
            cluster_id=CLUSTER_ID,
        ),
        routes={},
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 7: OrchestratorResponsesAgent

# COMMAND ----------

class OrchestratorResponsesAgent(ResponsesAgent):
    """MLflow ResponsesAgent with direct SQL/Genie tools and 2 specialist subagents."""

    def __init__(self):
        global model, memory_store

        # --- 1. Resolve skills directory ---
        _file_path = globals().get("__file__")
        skills_dir = SKILLS_DIR
        if _file_path:
            _this_dir = Path(_file_path).parent
            for candidate in [
                _this_dir / "skills",
                _this_dir / "code" / "skills",
                _this_dir.parent / "skills",
            ]:
                if candidate.exists():
                    skills_dir = candidate
                    break
        elif SKILLS_DIR.exists():
            skills_dir = SKILLS_DIR
        logger.info(f"Skills directory: {skills_dir}")
        self._skills_dir = skills_dir
        create_backend._skills_dir = skills_dir

        # Re-extract tables if skills_dir changed from default
        global _SKILL_TABLES_TEXT
        if skills_dir != SKILLS_DIR:
            _SKILL_TABLES_TEXT = _extract_tables_from_skills(skills_dir)
            logger.info(f"Re-extracted skill tables from {skills_dir}")

        # --- 2. Initialize model (inherited by all subagents) ---
        model = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)
        logger.info(f"LLM: {LLM_ENDPOINT_NAME} (inherited by all subagents)")

        # Lightweight model for background tasks (episodic memory enrichment, etc.)
        self._light_model = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME_LIGHT)
        logger.info(f"LLM (light): {LLM_ENDPOINT_NAME_LIGHT} (episodic memory enrichment)")

        # --- 3. Lazy DB init ---
        self._db_initialized = False
        self._db_init_lock = threading.Lock()

        # --- 4 & 5. Lakebase Postgres (checkpointer + store — NO fallback) ---
        # PostgresSaver + PostgresStore are fed psycopg_pool.ConnectionPool
        # instances so dead connections are recycled transparently between
        # requests (Lakebase rotates OAuth creds and drops idle sessions —
        # a single long-lived psycopg.Connection produced
        # OperationalError('the connection is closed') on multi-turn follow-ups).
        # No MemorySaver/InMemoryStore fallback — fail hard if Lakebase unavailable.
        # Lazy init (deferred to first predict_stream call) because LAKEBASE_URL
        # may not be available during log_model validation.
        self._checkpointer = None
        self._checkpointer_pool = None
        self._store_conn = None  # raw psycopg.Connection — see _init_checkpointer
        self._checkpointer_initialized = False

        # memory_store stays None until _init_checkpointer() sets PostgresStore.
        # No InMemoryStore fallback — hard-fail if Lakebase is unavailable.
        memory_store = None
        logger.info("memory_store=None (will be set to PostgresStore on first request)")

        # --- 6. Semantic Cache (Direct Access) ---
        global semantic_cache
        semantic_cache = SemanticCache(
            enabled=SEMANTIC_CACHE_ENABLED,
            endpoint_name=SEMANTIC_CACHE_ENDPOINT_NAME,
            index_name=SEMANTIC_CACHE_INDEX_NAME,
            embedding_endpoint=SEMANTIC_CACHE_EMBEDDING_ENDPOINT,
            similarity_threshold=SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
            ttl_hours=SEMANTIC_CACHE_TTL_HOURS,
        )
        logger.info(f"SemanticCache created (enabled={SEMANTIC_CACHE_ENABLED}, direct_access)")

        logger.info("OrchestratorResponsesAgent initialized (direct data + 2 subagents, DB init deferred)")

    @staticmethod
    def _url_to_duckdb_dsn(url: str) -> str:
        """Convert a psycopg connection URL to a DuckDB postgres-extension DSN.

        DuckDB's ``ATTACH ... (TYPE postgres)`` uses libpq-style DSN
        (space-delimited key=value), not a URL. Like psycopg, DuckDB's
        postgres extension supports both ``host`` (FQDN for TLS SNI) and
        ``hostaddr`` (IP for TCP bypass of DNS). We pass BOTH so that:
        - ``host=<FQDN>`` provides the TLS SNI hostname for the regional
          gateway to route to the correct Lakebase instance.
        - ``hostaddr=<IP>`` bypasses DNS resolution (private hostnames
          don't resolve from serverless / Model Serving containers).

        This mirrors the benchmark notebook (``duckdb_model_comparison.py``
        Cell 5) which proved this works cross-cloud (AWS → Azure Lakebase).
        """
        from urllib.parse import urlparse, parse_qs, unquote
        p = urlparse(url)
        params = parse_qs(p.query)
        pw = unquote(p.password or "")
        parts = [
            f"host={p.hostname}",
            f"port={p.port or 5432}",
            f"user={p.username}",
            f"password={pw}",
            f"dbname={p.path.lstrip('/')}",
            f"sslmode={(params.get('sslmode') or ['require'])[0]}",
        ]
        # Pass hostaddr if present — lets DuckDB skip DNS while keeping
        # the FQDN in host for TLS SNI routing.
        if "hostaddr" in params:
            parts.append(f"hostaddr={params['hostaddr'][0]}")
        return " ".join(parts)

    @staticmethod
    def _resolve_lakebase_url(base_url: str) -> str:
        """Ensure hostaddr= is present in Lakebase URL for serverless connectivity.

        If hostaddr is already in the URL (hardcoded), skip DoH resolution.
        Otherwise, resolve the regional gateway IP via Google DoH and append it.
        """
        if "hostaddr=" in base_url:
            logger.info("hostaddr already present in LAKEBASE_URL, skipping DoH resolution")
            return base_url
        import requests as _requests
        _gateway = os.environ.get(
            "LAKEBASE_REGIONAL_GATEWAY",
            _CFG.get("lakebase", {}).get("regional_gateway", "southeastasia.azuredatabricks.net"),
        )
        _fallback_ip = _CFG.get("lakebase", {}).get("fallback_ip", "20.247.134.0")
        # Iterate DoH answers and pick the first A record (type=1). Naive
        # `Answer[0].data` fails for CNAMEd hosts like Lakebase Autoscaling,
        # where the first answer is a CNAME to a privatelink hostname (not
        # an IP), and psycopg then rejects `hostaddr=<hostname>` with
        # "could not parse network address".
        actual_ip = None
        try:
            doh_url = f"https://dns.google/resolve?name={_gateway}&type=A"
            resp = _requests.get(doh_url, timeout=5).json()
            for ans in resp.get("Answer", []) or []:
                # DNS type 1 = A record
                if ans.get("type") == 1:
                    actual_ip = ans.get("data")
                    break
            if actual_ip:
                logger.info(f"DoH resolved {_gateway} → {actual_ip}")
            else:
                logger.warning(
                    f"DoH for {_gateway} returned no A record (likely CNAME-only). "
                    "Skipping hostaddr injection; psycopg will resolve via system DNS."
                )
        except Exception as e:
            logger.warning(f"DoH resolution failed ({e}), trying fallback IP {_fallback_ip}")
            actual_ip = _fallback_ip if _fallback_ip else None
        if not actual_ip:
            # No usable IP — let psycopg's own DNS resolver handle it. Works on
            # Free Edition Lakebase Autoscaling where public DNS resolves.
            return base_url
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}hostaddr={actual_ip}"

    def _init_checkpointer(self):
        """Lazy-initialize PostgresSaver checkpointer + PostgresStore (Lakebase).

        The InMemoryStore fallback shipped on 2026-05-13 made langmem writes
        evaporate on every container restart (memory tooling never appeared
        to fire in trace `tr-6ee96c6cb2dbdc8223933c89938ae7b7`). We're back
        on Postgres — pinned `langgraph-checkpoint-postgres==2.0.2`, the last
        version before `from psycopg import Capabilities` was added, which
        works against psycopg 3.1.19 (the Free-Edition-libpq-safe version).
        See the dependency pin matrix and the memory-not-firing note.

        Deferred from __init__ because LAKEBASE_URL may not be available
        during log_model validation. Called on first predict_stream request.
        No fallback — raises if Lakebase is unavailable.
        """
        if self._checkpointer_initialized:
            return
        import psycopg
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver
        from langgraph.store.postgres import PostgresStore

        _lakebase_url = os.environ.get(
            "LAKEBASE_URL",
            _CFG.get("lakebase", {}).get("url", ""),
        )
        if not _lakebase_url:
            raise ValueError(
                "LAKEBASE_URL is required for variable_store / query_stored_dfs. "
                "Set it in agents.deploy(environment_vars=...) or workspace_config.yml."
            )
        # Resolve IP via DoH for serverless/Model Serving environments.
        # On Free Edition Autoscaling the public DNS resolves directly, so
        # this is mostly a no-op there (see the Lakebase autoscaling notes),
        # but keep it for parity with work workspace.
        _lakebase_url = self._resolve_lakebase_url(_lakebase_url)

        # Pool sizing chosen for Model Serving: small (1-4) because each
        # serving replica is single-tenant for a thread_id and bursts are
        # rare. max_lifetime below Lakebase OAuth rotation horizon; max_idle
        # short so dead sockets don't linger. check_connection does a
        # cheap SELECT 1 before handing out a connection — closes the
        # OperationalError('the connection is closed') window between turns.
        _POOL_KW = dict(
            min_size=1, max_size=4,
            max_lifetime=600,          # recycle every 10 min
            max_idle=120,              # close idle after 2 min
            timeout=30,                # wait up to 30s for a conn
            check=ConnectionPool.check_connection,
            open=True,
        )

        # Pool 1: checkpointer — autocommit per LangGraph contract.
        # PostgresSaver 2.0.2 already accepts a ConnectionPool natively
        # (uses _get_connection() to extract a Connection per cursor call).
        self._checkpointer_pool = ConnectionPool(
            conninfo=_lakebase_url,
            kwargs={"autocommit": True},
            **_POOL_KW,
        )
        self._checkpointer = PostgresSaver(conn=self._checkpointer_pool)
        self._checkpointer.setup()
        logger.info("PostgresSaver initialized (Lakebase, ConnectionPool)")

        # PostgresStore — durable backing for langmem user-prefs namespace.
        # PostgresStore 2.0.2 ONLY accepts a raw Connection (pool support
        # was added in 2.0.4, which also added the Capabilities import we
        # can't satisfy on Free Edition). Use a single long-lived conn here.
        # langmem usage is sparse (one write when a user states a pref, one
        # read per orchestrator turn) so dropped-connection risk is low.
        # If it bites, _retrieve_user_prefs already swallows search failures
        # and the next request will re-enter _init_checkpointer.
        global memory_store
        self._store_conn = psycopg.connect(
            _lakebase_url,
            autocommit=True,
            row_factory=dict_row,
            prepare_threshold=0,
        )
        memory_store = PostgresStore(conn=self._store_conn)
        memory_store.setup()
        logger.info("PostgresStore initialized (Lakebase, raw Connection)")

        # LakebaseVariableStore + DuckDB DSN — variable_store/ still talks
        # to Lakebase via raw psycopg.connect() (one conn per op, no pool
        # needed since each operation is short-lived).
        _resolved_url = _lakebase_url
        from variable_store.lakebase_store import configure as _configure_vs
        _configure_vs(connection_factory=lambda: psycopg.connect(_resolved_url))
        logger.info("LakebaseVariableStore configured (connection_factory bound)")

        global _DUCKDB_LAKEBASE_DSN
        _DUCKDB_LAKEBASE_DSN = self._url_to_duckdb_dsn(_lakebase_url)
        logger.info("DuckDB Lakebase DSN computed for query_stored_dfs")

        self._checkpointer_initialized = True

    def _init_db(self):
        """Lazy-initialize WorkspaceClient(s).

        Constructs two clients:

        - ``_workspace_client``  — SP-mode, stable identity. Used for Vector
          Search reads, UC catalog list, episodic-memory writes, and chart
          Volume writes. Prefers OAuth client_id/secret (DATABRICKS_CLIENT_ID
          + DATABRICKS_CLIENT_SECRET injected via agents.deploy from the
          ``agent-secrets`` secret scope); falls back to DATABRICKS_TOKEN
          for the v2 legacy path.

        - ``_obo_workspace_client`` — OBO-mode, minted with
          ``ModelServingUserCredentials()``. Reads the forwarded
          ``X-Forwarded-Access-Token`` per call so Genie / SQL warehouse /
          notebook-write tools execute under the calling user's identity.
          Construction is best-effort: if the bridge package is missing or
          the env doesn't support OBO (local notebook validation), the
          client is left as None and tools fall back to the SP client.

        See the OBO dual-client pattern for why a single cached OBO client
        safely handles concurrent users (per-call header reads).
        """
        with self._db_init_lock:
            if self._db_initialized:
                return
            global _workspace_client, _obo_workspace_client
            _client_id = os.environ.get("DATABRICKS_CLIENT_ID", "").strip()
            _client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET", "").strip()
            if _client_id and _client_secret:
                _workspace_client = WorkspaceClient(
                    host=f"https://{DATABRICKS_HOST}",
                    client_id=_client_id,
                    client_secret=_client_secret,
                )
                logger.info("[AUTH] SP WorkspaceClient initialized via OAuth client_credentials")
            elif DATABRICKS_TOKEN:
                _workspace_client = WorkspaceClient(
                    host=f"https://{DATABRICKS_HOST}",
                    token=DATABRICKS_TOKEN,
                )
                logger.warning(
                    "[AUTH] SP WorkspaceClient initialized via legacy PAT "
                    "(DATABRICKS_TOKEN). Migrate to DATABRICKS_CLIENT_ID/SECRET "
                    "via agent-secrets scope on the next deploy."
                )
            else:
                _workspace_client = WorkspaceClient(host=f"https://{DATABRICKS_HOST}")
                logger.warning("[AUTH] SP WorkspaceClient: SDK auto-detect (no creds env)")

            # OBO client construction — separate try block so a missing
            # databricks-ai-bridge or non-Model-Serving runtime doesn't
            # block the SP path. Tools that need OBO fall back to SP if
            # this stays None (logged at first use).
            try:
                from databricks_ai_bridge import ModelServingUserCredentials
                _obo_workspace_client = WorkspaceClient(
                    host=f"https://{DATABRICKS_HOST}",
                    credentials_strategy=ModelServingUserCredentials(),
                )
                logger.info("[AUTH] OBO WorkspaceClient initialized (ModelServingUserCredentials)")
            except Exception as obo_err:
                _obo_workspace_client = None
                logger.warning(f"[AUTH] OBO WorkspaceClient unavailable: {obo_err}")

            self._db_initialized = True
            # Pre-create base directories and cache user email
            try:
                email = _workspace_client.current_user.me().user_name
                global _current_user_email
                _current_user_email = email
                _workspace_client.workspace.mkdirs(f"/Workspace/Users/{email}/agent_generated")
                logger.info(f"Workspace dir ensured for {email}")
            except Exception as e:
                logger.warning(f"Could not resolve user email: {e}")
            try:
                _workspace_client.files.create_directory(f"{_VOLUME_PATH}/data")
            except Exception:
                pass  # Already exists
            logger.info("Lazy DB initialization complete")

            # Cache UC catalog names for table name extraction
            try:
                global _uc_catalog_names
                _uc_catalog_names = {c.name for c in _workspace_client.catalogs.list() if c.name}
                logger.info(f"Cached {len(_uc_catalog_names)} UC catalogs: {_uc_catalog_names}")
            except Exception as e:
                logger.warning(f"Could not list UC catalogs: {e}")

    def create_production_agent(self, checkpointer: BaseCheckpointSaver):
        """Create the orchestrator agent with v2 factory tools + 2 subagents.

        **B3 wiring (plan Commit 5):** imports Group A tool factories and
        builds concrete tool instances with ``workspace_client``,
        ``VariableStore`` (now ``LakebaseVariableStore``), and warehouse/DSN
        deps baked in via closures. v1 inline tools that haven't been
        rewritten yet (``run_python_code``, ``store_dataframe``,
        ``list_dataframes``) are kept as-is — they now go through ``LakebaseVariableStore`` via
        the Cell 5 alias ``VariableStore = LakebaseVariableStore``.

        Subagent builders live in this package's ``subagents/``.
        Passing ``store=memory_store`` is still required for the DeepAgents
        ``InjectedStore()`` injection mechanism, even though
        ``LakebaseVariableStore`` ignores it internally.
        """

        from subagents import (
            build_python_analyst_subagent_dict,
            build_data_viz_subagent_dict,
        )

        # --- Build v2 factory tools (compact-ref returns, ~500 token budget) ---
        # Genie + SQL warehouse calls flow under the user's identity via OBO
        # so Unity Catalog row-level security, Genie space grants, and SQL
        # warehouse audit attribute correctly to the calling user.
        _ask_genie = build_ask_genie_space_tool(
            workspace_client=_user_workspace_client(),
            variable_store_cls=VariableStore,
            genie_timeout_seconds=GENIE_TIMEOUT_SECONDS,
        )
        _run_sql = build_run_spark_sql_tool(
            workspace_client=_user_workspace_client(),
            variable_store_cls=VariableStore,
            sql_warehouse_id=SQL_WAREHOUSE_ID,
            ensure_warehouse_running=_ensure_warehouse_running,
        )
        _describe_df = build_describe_dataframe_tool(
            variable_store_cls=VariableStore,
        )
        _query_dfs = build_query_stored_dfs_tool(
            variable_store_cls=VariableStore,
            lakebase_dsn=_DUCKDB_LAKEBASE_DSN,
        )
        # B2: split notebook tools
        _save_nb = build_save_python_notebook_tool(
            save_fn=_save_notebook_to_workspace,
            build_preamble_fn=_build_variable_store_preamble,
            variable_store_cls=VariableStore,
        )
        _run_nb = build_run_python_notebook_tool_v2(
            save_fn=_save_notebook_to_workspace,
            execute_fn=_execute_serverless,
            build_preamble_fn=_build_variable_store_preamble,
            parse_writebacks_fn=_parse_and_commit_writebacks,
            variable_store_cls=VariableStore,
            vs_sentinel=_VS_SENTINEL,
        )

        # Hackathon: D3 infographic rendering → Volumes HTML upload.
        # Replaces v3's Plotly render_chart per decision doc 2026-05-13.
        _compose_infographic = build_compose_infographic_tool(
            workspace_client=_workspace_client,
            variable_store_cls=VariableStore,
            app_url=APP_URL,
        )

        # Hackathon: freehand bespoke scrollytelling escape hatch. Safe — it does
        # NOT exec agent code; it injects an agent-computed `data` dict into an
        # agent-authored self-contained HTML template at the "__DATA__" token and
        # uploads. For standard charts/report stories use compose_infographic.
        _compose_story = build_compose_story_tool(
            workspace_client=_workspace_client,
            variable_store_cls=VariableStore,
            app_url=APP_URL,
        )

        # Hackathon: office-suite document generation (pptx/docx/xlsx/csv/pdf)
        # → Volumes binary upload via Files API. Added 2026-05-15 after
        # tr-83d056e1a485c06f8b19df47db7f08e3 showed run_python_code-generated
        # pptx bytes silently land in the serving container's tmpfs, not UC.
        _compose_document = build_compose_document_tool(
            workspace_client=_workspace_client,
            variable_store_cls=VariableStore,
            app_url=APP_URL,
        )

        # Hackathon: presentation decks (RA cobalt brand) → Volumes .pptx with
        # NATIVE PowerPoint charts + HTML preview, via python-pptx. Additive to
        # compose_document (which keeps docx/xlsx/csv/pdf). Template mode auto-
        # loads skills/compose-pptx/templates/ra_template.pptx when present
        # (override via COMPOSE_DECK_TEMPLATE env or template_path= kwarg).
        _compose_deck = build_compose_deck_tool(
            workspace_client=_workspace_client,
            variable_store_cls=VariableStore,
            app_url=APP_URL,
        )

        # Neo4j skills-brain: the ONE swap vs. the production orchestrator.
        # find_skill replaces the filesystem skill retrieval (auto-injected
        # SKILL.md overviews + a progressive-disclosure read_file walk over
        # /skills/) with a single graph round-trip that returns the relevant
        # skill chunks + routed skill folders. Embeds the query with the same
        # FM endpoint the graph was ingested with (no torch in the image).
        # Shared by the orchestrator AND both subagents — the brain ranks all
        # 8 skills, so the prompts (not a skill= prefix) steer each agent's
        # focus. See the Neo4j skills-graph design + tools/find_skill.py.
        _find_skill = build_find_skill_tool(
            embedding_endpoint=FIND_SKILL_EMBED_ENDPOINT,
            result_k=FIND_SKILL_RESULT_K,
            workspace_client=_workspace_client,
            app_url=APP_URL,
            volume_dir=f"{_VOLUME_PATH}/skill_graphs",
            render_graph=FIND_SKILL_RENDER_GRAPH,
        )

        # --- Dict-based subagents ---
        # NOTE (neo4j fork): the `skills=` scoping (which mounted FilesystemBackend
        # skill folders + auto-injected their overviews) is REMOVED. Each subagent
        # now gets the find_skill tool and discovers the relevant material via the
        # graph; the system prompts already tell python-analyst to look at the data
        # domains and data-viz at the design system. create_deep_agent still
        # handles store propagation automatically.
        python_analyst = build_python_analyst_subagent_dict(
            tools=[
                _find_skill,         # Neo4j skills-brain (domain schemas + SQL patterns)
                _run_sql,            # Genie fallback (v2 compact-ref)
                _query_dfs,          # DuckDB fast-path on stored dfs (v2)
                _describe_df,        # Explore stored dfs (v2, replaces get_dataframe)
                think_tool,          # Scratch-pad reasoning (v2)
                run_python_code,     # In-process exec (v1 inline)
                _run_nb,             # Serverless exec (v2 B2 — ephemeral)
                _save_nb,            # Save-only notebook (v2 B2)
                _compose_document,   # Office-suite docs → UC Volumes (binary-safe)
                store_dataframe,     # Manual store (v1 inline)
                list_dataframes,     # List stored (v1 inline)
            ],
            system_prompt=PYTHON_ANALYST_PROMPT,
        )

        data_viz = build_data_viz_subagent_dict(
            tools=[
                _find_skill,           # Neo4j skills-brain (design system + chart guidance)
                _compose_infographic,  # D3 scene engine → Volumes HTML (single chart or report story)
                _compose_story,        # Freehand bespoke scrollytelling → Volumes HTML
                # think_tool removed 2026-06-12 (eval round): on a reasoning
                # model the mandated reflection duplicated hidden CoT and cost
                # one full LLM round-trip per delegation + 1.3k schema chars.
                _describe_df,          # Explore stored dfs (v2)
                list_dataframes,       # List stored (v1 inline)
            ],
            system_prompt=DATA_VIZ_PROMPT,
        )

        _orchestrator_tools = [
            # Neo4j skills-brain — call FIRST to route to the right skill
            _find_skill,
            # v2 factory tools (compact-ref returns)
            _ask_genie,          # PRIMARY data retrieval
            _query_dfs,          # DuckDB fast-path on stored data
            _describe_df,        # Explore stored dfs (replaces get_dataframe)
            # v1 inline tools
            store_dataframe,
            _compose_infographic,  # D3 scene engine → Volumes HTML (single chart or report story)
            _compose_story,        # Freehand bespoke scrollytelling → Volumes HTML
            _compose_document,     # Office-suite docs → Volumes binary (hackathon)
            _compose_deck,         # Presentation decks → Volumes pptx + HTML (RA brand)
            list_dataframes,
            # NOTE (B4): run_spark_sql + run_python_notebook removed from
            # orchestrator per plan. Orchestrator delegates to python-analyst
            # for SQL fallback + notebook execution.
        ]
        if USER_PREFS_ENABLED and save_user_preference is not None:
            _orchestrator_tools.append(save_user_preference)

        logger.warning(
            f"[user-prefs:agent-build] USER_PREFS_ENABLED={USER_PREFS_ENABLED} "
            f"save_user_preference_present={save_user_preference is not None} "
            f"orchestrator_tool_count={len(_orchestrator_tools)} "
            f"orchestrator_tool_names={[getattr(t, 'name', '?') for t in _orchestrator_tools]}"
        )

        # NOTE (neo4j fork): `skills=["/skills/"]` is REMOVED. That parameter
        # drove DeepAgents' SkillsMiddleware — it auto-injected every SKILL.md
        # overview into the system prompt and expected the agent to walk
        # /skills/ with read_file. That filesystem retrieval is exactly what
        # find_skill replaces. The CompositeBackend still mounts /skills/ (see
        # create_backend), so read_file('/skills/<doc_path>') remains available
        # as a full-file fallback after find_skill points the agent at a doc.
        return create_deep_agent(
            model=model,
            tools=_orchestrator_tools,
            system_prompt=ORCHESTRATOR_PROMPT,
            subagents=[python_analyst, data_viz],
            middleware=[
                ModelServingToolFilterMiddleware(),
                FailedToolPruningMiddleware(),
            ],
            backend=create_backend,
            checkpointer=checkpointer,
            store=memory_store,
        )

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        outputs = [
            event.item
            for event in self.predict_stream(request)
            if event.type == "response.output_item.done"
        ]
        return ResponsesAgentResponse(output=outputs, custom_outputs=request.custom_inputs)

    @staticmethod
    def _extract_fq_tables(text: str) -> List[str]:
        """Extract fully qualified table names (catalog.schema.table) from text.

        Handles both unquoted (catalog.schema.table) and backtick-quoted
        (`catalog`.`schema`.`table`) forms used by Genie SQL.
        Only returns matches whose first segment is a known UC catalog,
        filtering out Python dot-paths like dbutils.notebook.exit.
        """
        _text = text or ""
        # Unquoted: catalog.schema.table
        unquoted = set(re.findall(r'\b([a-zA-Z_]\w*\.[a-zA-Z_]\w*\.[a-zA-Z_]\w*)\b', _text))
        # Backtick-quoted: `catalog`.`schema`.`table`
        quoted = set(re.findall(r'`([^`]+)`\.`([^`]+)`\.`([^`]+)`', _text))
        matches = unquoted | {f"{c}.{s}.{t}" for c, s, t in quoted}
        if _uc_catalog_names:
            return [m for m in matches if m.split(".")[0] in _uc_catalog_names]
        return list(matches)

    def predict_stream(
        self, request: ResponsesAgentRequest
    ) -> Generator[ResponsesAgentStreamEvent, None, None]:
        if not self._db_initialized:
            self._init_db()
        if not self._checkpointer_initialized:
            self._init_checkpointer()

        # Extract thread_id
        ci = dict(request.custom_inputs or {})
        _thread_id_source = "custom_inputs"
        if "thread_id" not in ci:
            if request.context and getattr(request.context, "conversation_id", None):
                ci["thread_id"] = request.context.conversation_id
                _thread_id_source = "context.conversation_id"
            else:
                ci["thread_id"] = str(uuid.uuid4())
                _thread_id_source = "generated_uuid"
        # [v3-debug] Log thread_id resolution path so we can tell whether
        # multi-turn breaks because the conversation_id never reached the
        # endpoint (frontend/provider issue) vs. checkpoint load failed
        # (Lakebase/postgres issue). Distinguishing these is hard without
        # this line because both produce identical agent behaviour
        # ("forgets" prior turns).
        _ctx_obj = request.context
        _ctx_attrs = (
            {a: getattr(_ctx_obj, a, None) for a in ("conversation_id", "user_id", "user_name", "email")}
            if _ctx_obj is not None else {}
        )
        # WARNING level on purpose — Model Serving's stdout capture filters
        # out INFO-level records (only WARNING+ reach the Logs API).
        logger.warning(
            f"[v3-debug:thread_id] resolved={ci['thread_id']} source={_thread_id_source} "
            f"context_attrs={_ctx_attrs} custom_inputs_keys={list((request.custom_inputs or {}).keys())}"
        )

        # Extract user_id: custom_inputs > request.context > MLflow headers > fallback
        if "user_id" not in ci:
            _resolved_user = None

            # # 1. Try request.context attributes
            # _ctx = request.context
            # if _ctx:
            #     for _attr in ("user_name", "username", "user_id", "email"):
            #         _val = getattr(_ctx, _attr, None)
            #         if _val:
            #             _resolved_user = _val
            #             break
            #     logger.warning(f"[user_id] request.context type={type(_ctx).__name__}, "
            #                    f"attrs={[a for a in dir(_ctx) if not a.startswith('_')]}, "
            #                    f"resolved={_resolved_user}")

            # # 2. Try MLflow request headers (Databricks injects user identity)
            # if not _resolved_user:
            #     try:
            #         from mlflow.pyfunc.context import Context as _MlflowContext
            #         _headers = getattr(_MlflowContext, "request_headers", None)
            #         if callable(_headers):
            #             _headers = _headers()
            #         if isinstance(_headers, dict):
            #             _resolved_user = (
            #                 _headers.get("X-Forwarded-Email")
            #                 or _headers.get("X-Forwarded-User")
            #                 or _headers.get("X-Databricks-User")
            #             )
            #             logger.warning(f"[user_id] MLflow headers keys={list(_headers.keys())}, resolved={_resolved_user}")
            #     except Exception as _hdr_err:
            #         logger.warning(f"[user_id] MLflow headers failed: {_hdr_err}")
            
            # 1. Try OBO WorkspaceClient
            if not _resolved_user:
                # logger.warning("[user_id:debug] MLflow headers failed, trying OBO WorkspaceClient...")
                logger.warning("[user_id] extracting user id from OBO WorkspaceClient...")
                try:
                    _obo_client = _user_workspace_client()
                    logger.warning(
                        f"[user_id:debug] OBO client type={type(_obo_client).__name__}, "
                        f"host={getattr(getattr(_obo_client, 'config', None), 'host', 'N/A')}, "
                        f"auth_type={getattr(getattr(_obo_client, 'config', None), 'auth_type', 'N/A')}"
                    )
                    _me = _obo_client.current_user.me()
                    logger.warning(
                        f"[user_id:debug] OBO current_user.me() returned: "
                        f"user_name={_me.user_name!r}, display_name={_me.display_name!r}, "
                        f"id={_me.id!r}, emails={getattr(_me, 'emails', None)!r}"
                    )
                    _resolved_user = _me.user_name
                    if _resolved_user:
                        logger.warning(f"[user_id] from OBO WorkspaceClient: {_resolved_user}")
                except Exception as _obo_err:
                    logger.warning(
                        f"[user_id:debug] OBO current_user.me() failed: "
                        f"{type(_obo_err).__name__}: {_obo_err}"
                    )

            ci["user_id"] = _resolved_user or "default_user"
            logger.warning(f"[user_id] final={ci['user_id']}")

        request.custom_inputs = ci
        thread_id = ci["thread_id"]

        # Extract messages — only pass last user message (checkpointer loads history)
        def _extract_text(content) -> str:
            if isinstance(content, list):
                return " ".join(item.text for item in content if hasattr(item, "text"))
            return str(content) if content else ""

        last_user_message = None
        if request.input:
            for msg in request.input:
                if not hasattr(msg, "content") or not hasattr(msg, "role"):
                    continue
                text = _extract_text(msg.content)
                if not text:
                    continue
                if getattr(msg, "role", "user") == "user":
                    last_user_message = HumanMessage(content=text)

        if not last_user_message:
            last_user_message = HumanMessage(content="Hello")

        langchain_messages = [last_user_message]
        user_message_text = last_user_message.content

        logger.info(f"[predict_stream] thread_id={thread_id}")

        is_first_turn = len(request.input) == 1

        # NOTE: render_chart and other tools read `user_id` from
        # `configurable` for path scoping. Set BOTH keys — the
        # `langgraph_user_id` form is what LangGraph internals look at
        # (and what langmem substitutes into namespace tuples), the bare
        # `user_id` form is what tool factories expect. Without `user_id`
        # here every chart lands under `/charts/default/...`.
        # `langgraph_user_id` is sanitized for use as a BaseStore namespace
        # label — LangGraph rejects periods and most punctuation. Keep the
        # raw email in `user_id` for path scoping; use the sanitized form
        # only for the LangGraph-internal/langmem path.
        _raw_user_id = ci.get("user_id", "default_user")
        _ns_user_id = re.sub(r"[^A-Za-z0-9_-]", "_", _raw_user_id) or "default_user"
        checkpoint_config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": _raw_user_id,
                "langgraph_user_id": _ns_user_id,
            }
        }

        # --- Semantic cache check (first-turn only) ---
        if is_first_turn and semantic_cache:
            cached_answer = semantic_cache.get(user_message_text)
            if cached_answer:
                logger.info("[Semantic Cache HIT] Returning cached response")
                # Write Q&A to checkpoint so follow-up turns have conversation history
                try:
                    agent = self.create_production_agent(self._checkpointer)
                    cached_ai_msg = AIMessage(content=cached_answer)
                    agent.update_state(
                        checkpoint_config,
                        {"messages": [last_user_message, cached_ai_msg]},
                    )
                    logger.info("[Semantic Cache] Persisted Q&A to checkpoint for multi-turn")
                except Exception as e:
                    logger.warning(f"[Semantic Cache] Failed to persist to checkpoint: {e}")
                yield from output_to_responses_items_stream([AIMessage(content=cached_answer)])
                return

        # --- Episodic memory recall (inject prior context) ---
        if is_first_turn and EPISODIC_VS_ENABLED:
            try:
                with mlflow.start_span(name="episodic_memory_recall", span_type="RETRIEVER") as span:
                    span.set_inputs({"query": user_message_text, "num_results": EPISODIC_VS_NUM_RESULTS,
                                     "score_threshold": EPISODIC_VS_SCORE_THRESHOLD})
                    recall_result = recall_past_analysis(
                        query=user_message_text,
                        vs_endpoint=EPISODIC_VS_ENDPOINT_NAME,
                        vs_index=EPISODIC_VS_INDEX_NAME,
                        enabled=EPISODIC_VS_ENABLED,
                        num_results=EPISODIC_VS_NUM_RESULTS,
                        score_threshold=EPISODIC_VS_SCORE_THRESHOLD,
                    )
                    episodic_context = format_episodic_context(recall_result)
                    span.set_outputs({
                        "status": recall_result.get("status"),
                        "total_memories_found": recall_result.get("total_memories_found", 0),
                        "ranked_memories": recall_result.get("ranked_memories", []),
                        "context_injected": bool(episodic_context),
                        "context_chars": len(episodic_context),
                        "formatted_context": episodic_context or "(none)",
                    })
                    if episodic_context:
                        langchain_messages = [HumanMessage(content=f"{episodic_context}\n{user_message_text}")]
                        logger.info(f"[Episodic Recall] Injected {len(episodic_context)} chars of prior context "
                                    f"({recall_result.get('total_memories_found', 0)} memories)")
                        logger.debug(f"[Episodic Recall] Full injected message:\n{langchain_messages[0].content}")
            except Exception as e:
                logger.warning(f"[Episodic Recall] Failed, proceeding without context: {e}")

        # --- User preferences (per-user, every turn) ---
        # Reads the langmem-managed namespace ("user_prefs", <user_id>) under
        # the OBO-resolved identity. Never quotes recalled facts — see
        # the user-preferences memory pattern + the orchestrator prompt's
        # "User Preferences" section. Skipped silently for default_user
        # (no OBO identity resolved).
        if USER_PREFS_ENABLED and memory_store is not None:
            try:
                _resolved_user = checkpoint_config["configurable"].get("langgraph_user_id", "default_user")
                _prefs_block = _retrieve_user_prefs(
                    memory_store, _resolved_user, user_message_text,
                    limit=USER_PREFS_NUM_RESULTS,
                )
                if _prefs_block:
                    _existing = langchain_messages[0].content
                    langchain_messages = [HumanMessage(content=f"{_prefs_block}\n\n{_existing}")]
                    logger.info(f"[user-prefs] injected {len(_prefs_block)} chars for user={_resolved_user}")
            except Exception as e:
                logger.warning(f"[user-prefs] retrieval failed (skipping): {e}")

        agent = self.create_production_agent(self._checkpointer)

        # Snapshot existing checkpoint message IDs to avoid re-streaming.
        # [v3-debug] Verbose logging here lets us tell apart "checkpoint
        # write succeeded last turn but read returned None this turn"
        # (Lakebase/postgres state lost) vs. "fresh thread_id, never
        # written" (provider/frontend not propagating conversation_id).
        existing_msg_ids = set()
        _checkpoint_status = "unknown"
        try:
            checkpoint_tuple = self._checkpointer.get_tuple(checkpoint_config)
            if checkpoint_tuple is None:
                _checkpoint_status = "none"
            elif not checkpoint_tuple.checkpoint:
                _checkpoint_status = "empty"
            else:
                _checkpoint_status = "loaded"
                channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
                existing_msgs = channel_values.get("messages", [])
                for m in existing_msgs:
                    if hasattr(m, "id") and m.id:
                        existing_msg_ids.add(m.id)
            logger.warning(
                f"[v3-debug:checkpoint] status={_checkpoint_status} "
                f"existing_msg_count={len(existing_msg_ids)} "
                f"thread_id={thread_id} is_first_turn={is_first_turn}"
            )
        except Exception as e:
            _checkpoint_status = f"error:{type(e).__name__}"
            logger.warning(
                f"[v3-debug:checkpoint] FAILED to snapshot status={_checkpoint_status} "
                f"thread_id={thread_id} err={e}"
            )

        final_answer_text = None

        # --- Capture trace_id EARLY while MLflow span is still active ---
        _trace_id = None
        try:
            _active_span = mlflow.get_current_active_span()
            logger.info(f"[trace_id:EARLY] active_span={_active_span}, type={type(_active_span).__name__}")
            if _active_span:
                _trace_id = _active_span.trace_id
                logger.info(f"[trace_id:EARLY] captured trace_id={_trace_id}")
        except Exception as e:
            logger.warning(f"[trace_id:EARLY] failed: {e}")

        # --- Episodic memory trackers ---
        _trace_tools_used: set = set()
        _trace_queries: list = []
        _trace_tables: set = set()
        _trace_subagents: set = {"orchestrator"}
        _trace_genie_ids: set = set()
        _trace_warnings: list = []
        _trace_skills_used: set = set()
        _trace_dashboard_urls: list = []

        _known_subagent_names = {"python-analyst", "data-viz"}

        # [v3-debug] Intra-stream dedup. Without this set, the same AIMessage
        # bubbling up from a subagent through the orchestrator's super-step
        # is yielded twice — visible as duplicate paragraphs in the UI.
        # `existing_msg_ids` only catches multi-turn re-streaming (checkpoint
        # snapshot from PRIOR turns) — it does not see msgs streamed earlier
        # in THIS turn.
        _streamed_msg_ids: set[str] = set()
        _stream_msg_count = 0
        _stream_dup_count = 0

        _start_trace()
        for chunk in agent.stream({"messages": langchain_messages}, checkpoint_config):
            for node_name, node_output in chunk.items():
                if node_name in _known_subagent_names:
                    _trace_subagents.add(node_name)
                if node_output and isinstance(node_output, dict) and "messages" in node_output:
                    messages = node_output["messages"]
                    # Handle LangGraph Overwrite objects
                    if hasattr(messages, "value"):
                        messages = messages.value
                    if not isinstance(messages, list):
                        messages = [messages] if messages else []
                    for msg in messages:
                        if isinstance(msg, (AIMessage, AIMessageChunk, ToolMessage)):
                            msg_id = getattr(msg, "id", None)
                            if msg_id and msg_id in existing_msg_ids:
                                continue
                            if msg_id and msg_id in _streamed_msg_ids:
                                _stream_dup_count += 1
                                logger.warning(
                                    f"[v3-debug:dedup] skipping duplicate msg_id={msg_id} "
                                    f"node={node_name} type={type(msg).__name__}"
                                )
                                continue
                            if msg_id:
                                _streamed_msg_ids.add(msg_id)
                            _stream_msg_count += 1

                            # --- Track tool calls for episodic memory ---
                            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                                for tc in msg.tool_calls:
                                    tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                                    tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                                    if tc_name:
                                        _trace_tools_used.add(tc_name)
                                    if tc_name == "ask_genie_space" and tc_args.get("space_id"):
                                        _trace_genie_ids.add(tc_args["space_id"])
                                    if tc_name == "task" and tc_args:
                                        for _v in tc_args.values():
                                            if isinstance(_v, str) and _v in _known_subagent_names:
                                                _trace_subagents.add(_v)
                                                break
                                    if tc_name == "read_file":
                                        _path = tc_args.get("file_path", "")
                                        if "/skills/" in _path:
                                            _suffix = _path.split("/skills/", 1)[-1]
                                            _skill_dir = "/".join(_suffix.split("/")[:-1])
                                            if _skill_dir:
                                                _trace_skills_used.add(_skill_dir)

                            # --- Track warnings and dashboard URLs from tool responses ---
                            if isinstance(msg, ToolMessage):
                                content = str(getattr(msg, "content", ""))
                                _tool_name = getattr(msg, "name", "") or "unknown_tool"
                                if getattr(msg, "status", None) == "error":
                                    _first_line = content.splitlines()[0].strip() if content.strip() else "unknown error"
                                    _trace_warnings.append(f"{_tool_name}: {_first_line[:120]}")
                                for _url_match in re.findall(r'(https://[^\s)]+/#notebook/\d+)', content):
                                    _trace_dashboard_urls.append(_url_match)

                            yield from output_to_responses_items_stream([msg])
                            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                                _content = msg.content
                                if isinstance(_content, list):
                                    _content = " ".join(
                                        b.get("text", "") if isinstance(b, dict) else str(b)
                                        for b in _content
                                    )
                                final_answer_text = str(_content) if _content else ""

        # [v3-debug] Stream summary: yielded vs deduped vs from-checkpoint.
        # If dup_count > 0 the intra-stream dedup is doing real work.
        # If yielded_count == 0 and existing_msg_count == 0 the agent
        # produced nothing — usually means an upstream tool errored or the
        # checkpoint write didn't happen.
        logger.warning(
            f"[v3-debug:stream-summary] thread_id={thread_id} "
            f"yielded={_stream_msg_count} intra_stream_dups_skipped={_stream_dup_count} "
            f"checkpoint_msgs_skipped={len(existing_msg_ids)} "
            f"final_answer_present={bool(final_answer_text)}"
        )

        # --- Drain trace collector (SQL from all tools, including subagents) ---
        # Tools record their full SQL via trace_collector.record_sql() at
        # execution time (same thread). This works regardless of whether
        # the tool runs in the orchestrator or inside a subagent.
        for _sql in _drain_tool_queries():
            if _sql not in _trace_queries:
                _trace_queries.append(_sql)
                _trace_tables.update(self._extract_fq_tables(_sql))

        # --- Store in cache (first-turn only) ---
        if is_first_turn and final_answer_text and semantic_cache:
            try:
                semantic_cache.store(user_message_text, final_answer_text)
            except Exception as e:
                logger.warning(f"Cache store failed: {e}")

        # --- Resolve trace_id from MLflow ---
        try:
            _active = mlflow.get_current_active_span()
            if _active:
                _trace_id = _active.trace_id
        except Exception:
            pass
        if not _trace_id:
            try:
                _last_trace = mlflow.get_last_active_trace()
                if _last_trace:
                    _trace_id = _last_trace.info.request_id
                    logger.info(f"[trace_id:POST] from last_trace={_trace_id}")
            except Exception as e:
                logger.warning(f"[trace_id:POST] last_trace failed: {e}")
        if not _trace_id:
            _ctx = getattr(request, "context", None)
            if _ctx:
                _trace_id = getattr(_ctx, "databricks_request_id", None) or getattr(_ctx, "request_id", None)
        if not _trace_id:
            _trace_id = f"no_trace_{thread_id}"

        # --- Log to episodic memory ---
        log_to_episodic_memory(
            trace_id=_trace_id,
            user_question=user_message_text,
            agent_response=final_answer_text or "",
            thread_id=thread_id,
            user_id=ci.get("user_id", "default_user"),
            queries_executed=_trace_queries,
            tables_accessed=_trace_tables,
            tools_used=_trace_tools_used,
            nodes_executed=_trace_subagents,
            genie_space_ids=_trace_genie_ids,
            warnings=_trace_warnings,
            skills_used=_trace_skills_used,
            dashboard_urls=_trace_dashboard_urls,
            llm=self._light_model,
            workspace_client=_workspace_client,
            sql_warehouse_id=SQL_WAREHOUSE_ID,
            episodic_memory_table=EPISODIC_MEMORY_TABLE,
        )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 8: MLflow Export

# COMMAND ----------

AGENT = OrchestratorResponsesAgent()

if _TRACING_ENABLED:
    # CRITICAL: set tracking URI to Databricks BEFORE set_experiment / autolog,
    # otherwise mlflow falls through to a local sqlite store inside the serving
    # container. Symptoms when missing: "Experiment with name ... does not
    # exist. Creating a new experiment" log followed by every export attempt
    # failing with `RESOURCE_DOES_NOT_EXIST: Node ID 1 does not exist`. The
    # set_tracking_uri call was previously only inside the deploy block at
    # log_model time, which never runs in the serving container at runtime.
    try:
        mlflow.set_tracking_uri("databricks")
    except Exception as e:
        logger.warning(f"Failed to set tracking URI to databricks: {e}")
    _auto_exp_id = os.environ.get("MLFLOW_EXPERIMENT_ID")
    if _auto_exp_id:
        logger.warning(f"Using Databricks-assigned MLFLOW_EXPERIMENT_ID={_auto_exp_id}")
    else:
        _exp_name = os.environ.get(
            "MLFLOW_EXPERIMENT_NAME",
            _CFG.get("mlflow", {}).get("experiment_name", ""),
        )
        try:
            mlflow.set_experiment(_exp_name)
            logger.warning(f"MLflow experiment set to {_exp_name}")
        except Exception as e:
            logger.warning(f"Failed to set experiment: {e}")
    try:
        mlflow.langchain.autolog(log_traces=True, log_models=False)
    except TypeError:
        mlflow.langchain.autolog(log_traces=True)
    except Exception as e:
        logger.error(f"autolog failed: {e}")
else:
    logger.info("MLflow tracing disabled")

mlflow.models.set_model(AGENT)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 9: Log Model (run manually)
# MAGIC
# MAGIC Gated by `DEPLOY_V2=1` env var. Off by default so `%run ./deploy_orchestrator_agent`
# MAGIC from `lab_smoke_test.py` Test 9 doesn't trigger `log_model`. The
# MAGIC old `if __name__ == "__main__":` guard leaked because `%run` preserves
# MAGIC `__name__ == "__main__"` from the calling notebook.

# COMMAND ----------

# Helper: check DEPLOY_V2 from env var OR notebook widget (Jobs API base_parameters).
# Default is OFF so the serving container never fires Cells 9/10/12.
def _deploy_v2_enabled() -> bool:
    flag = os.environ.get("DEPLOY_V2", "")
    if not flag:
        try:
            flag = dbutils.widgets.get("DEPLOY_V2")  # type: ignore[name-defined]
        except Exception:
            pass
    return str(flag).lower() in ("1", "true", "yes")


# DEPLOY_V3: separate UC model + auto-derived endpoint (UC model name and
# endpoint name are both config-driven; never hardcode a UC catalog). Implies
# the broader OBO scope set; tool-side OBO clients are gated by the env var
# below at request time. The v2 endpoint stays untouched as the rollback baseline.
def _deploy_v3_enabled() -> bool:
    flag = os.environ.get("DEPLOY_V3", "")
    if not flag:
        try:
            flag = dbutils.widgets.get("DEPLOY_V3")  # type: ignore[name-defined]
        except Exception:
            pass
    return str(flag).lower() in ("1", "true", "yes")


def _deploy_enabled() -> bool:
    return _deploy_v2_enabled() or _deploy_v3_enabled()


def _resolve_uc_model_name() -> str:
    # Always read from workspace_config.yml — the catalog/schema/model prefix is
    # derived from config and never hardcoded to a UC catalog, so this works
    # across workspaces (e.g. Free Edition uses `workspace.hackathon.*`).
    return _CFG.get("mlflow", {}).get("uc_model_name", "")


def _resolve_endpoint_name() -> str:
    return _CFG.get("serving", {}).get("endpoint_name", "")


# Guard: skip during log_model validation (active_run is already set by log_model)
if _deploy_enabled() and not mlflow.active_run():
    # Hackathon: DatabricksVectorSearchIndex dropped with episodic memory.
    from mlflow.models.resources import (
        DatabricksServingEndpoint,
        DatabricksTable,
        DatabricksSQLWarehouse,
    )
    from mlflow.models.auth_policy import SystemAuthPolicy, UserAuthPolicy, AuthPolicy

    try:
        _notebook_path = (
            dbutils.notebook.entry_point  # noqa: F821
            .getDbutils().notebook().getContext().notebookPath().get()
        )
    except (AttributeError, TypeError):
        # Fallback for environments where dbutils is mocked (e.g. log_model validation)
        _notebook_path = "/Workspace/Users/default/deploy_orchestrator_agent"
    _model_code_path = f"/Workspace{_notebook_path}" if not _notebook_path.startswith("/Workspace") else _notebook_path
    _model_dir = os.path.dirname(_model_code_path)

    uc_model_name = _resolve_uc_model_name()

    resources = [
        DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT_NAME),
    ]
    # Light model is called by util.episodic_memory.enrich_episodic_memory()
    # via ChatDatabricks(endpoint=LLM_ENDPOINT_NAME_LIGHT). Without this in
    # resources, the system_auth_policy token is NOT scoped to query the
    # LIGHT endpoint and every enrichment call 403s with PERMISSION_DENIED
    # (trace `tr-5b6e7d6efbc72f26ad0bb60aa224195e`, 2026-05-05).
    if LLM_ENDPOINT_NAME_LIGHT and LLM_ENDPOINT_NAME_LIGHT != LLM_ENDPOINT_NAME:
        resources.append(DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT_NAME_LIGHT))

    # Episodic memory (VS index + Delta table) dropped for hackathon —
    # decisions doc 2026-05-13. EPISODIC_VS_INDEX_NAME and
    # EPISODIC_MEMORY_TABLE are inert stubs; no resources declared.
    # SQL warehouse the agent uses for tool calls (run_spark_sql, statement
    # execution for the rating endpoint, etc.).
    if SQL_WAREHOUSE_ID:
        resources.append(DatabricksSQLWarehouse(warehouse_id=SQL_WAREHOUSE_ID))

    input_example = {
        "input": [{"role": "user", "content": "Which districts have the most healthcare facilities?"}],
        "context": {"conversation_id": "example-123"},
    }

    system_auth_policy = SystemAuthPolicy(resources=resources)
    # v3: expand scopes so the forwarded user token can call Genie + SQL
    # warehouse + workspace API as the user. v2 keeps the minimal set.
    if _deploy_v3_enabled():
        _user_api_scopes = [
            "serving.serving-endpoints",   # call this endpoint as the user
            "sql.statement-execution",     # SQL warehouse via Statement Execution API
            "sql.warehouses",              # warehouse metadata
            "dashboards.genie",            # Genie API
            "catalog.connections",         # Lakehouse Federation / Genie cross-source
        ]
    else:
        _user_api_scopes = ["serving.serving-endpoints"]
    user_auth_policy = UserAuthPolicy(api_scopes=_user_api_scopes)

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")

    # Pin the experiment per UC model name BEFORE start_run so the model
    # version's bound experiment matches the one Model Serving will write
    # traces to at runtime. Without this, log_model() falls through to the
    # workspace_config.yml v2 experiment and v3 traces silently land in v2
    # (or get dropped because the runtime MLFLOW_EXPERIMENT_NAME mismatches
    # the model's bound experiment, breaking the async export queue with a
    # `Node ID 1 does not exist` error). Mirrors the env_vars logic below.
    _logmodel_exp_name = (
        f"/Shared/{uc_model_name}_traces"
        if _deploy_v3_enabled()
        else _CFG.get("mlflow", {}).get("experiment_name", "")
    )
    if _logmodel_exp_name:
        try:
            mlflow.set_experiment(_logmodel_exp_name)
            logger.info(f"log_model experiment pinned to {_logmodel_exp_name}")
        except Exception as e:
            logger.warning(f"Failed to pin log_model experiment {_logmodel_exp_name}: {e}")

    with mlflow.start_run():
        mlflow.pyfunc.log_model(
            name="agent",
            registered_model_name=uc_model_name,
            python_model=_model_code_path,
            code_paths=[
                os.path.join(_model_dir, "skills"),
                os.path.join(_model_dir, "backend.py"),
                os.path.join(_model_dir, "subagents"),
                os.path.join(_model_dir, "tools"),
                os.path.join(_model_dir, "util"),
                os.path.join(_model_dir, "variable_store"),
                os.path.join(_model_dir, "middleware"),
                # Neo4j skills-brain (find_skill retrieval) — vendored copy of
                # the brain's retrieval modules (config/db/embed/extract/retrieve).
                os.path.join(_model_dir, "brain"),
                os.path.join(_model_dir, "workspace_config.yml"),
            ],
            pip_requirements=[
                "mlflow[databricks]>=3.1.0",
                "deepagents>=0.4.11",
                "databricks-langchain>=0.15.0",
                "databricks-ai-bridge>=0.6.0",
                # langgraph-prebuilt 1.0.12 added a required `tools` arg to
                # ToolRuntime.__init__() that deepagents 0.5.3 doesn't pass
                # → "TypeError: ToolRuntime.__init__() missing 1 required
                # positional argument: 'tools'" in skills middleware before_agent.
                # v44 (last known good, 2026-04-24) had langgraph-prebuilt 1.0.10.
                # Pin until deepagents ships a compatible release.
                "langgraph>=1.1.3,<1.1.10",
                "langgraph-prebuilt==1.0.10",
                "langchain>=1.2.12",
                "langchain-core>=0.3.0",
                # langgraph-checkpoint-postgres 2.0.2 is the last release
                # before `from psycopg import Capabilities` was added (2.0.3+).
                # Compatible with psycopg 3.1.19, the Free-Edition-libpq-safe
                # version. Restores durable LangGraph checkpoint + langmem
                # PostgresStore against Lakebase. See the dependency pin matrix
                # + the memory-not-firing note.
                "langgraph-checkpoint-postgres==2.0.2",
                "psycopg==3.1.19",
                "psycopg-binary==3.1.19",
                "psycopg_pool",
                "databricks-agents",
                "databricks-sdk>=0.60.0",
                "pydantic>=2.0.0",
                "pyyaml",
                "duckdb>=0.10.0",
                "langmem",
                # Office-suite document generation for compose_document
                # (added 2026-05-15). All pure-Python so they install cleanly
                # in the serving build sandbox.
                "python-pptx>=0.6.21",
                "python-docx>=1.0.0",
                "openpyxl>=3.1.0",
                "reportlab>=4.0.0",
                # Neo4j skills-brain (find_skill). The driver is the ONLY new
                # dependency vs. the production orchestrator — the query
                # embedding reuses databricks-langchain's DatabricksEmbeddings,
                # so NO torch / sentence-transformers ships in the image.
                "neo4j>=5.20",
            ],
            input_example=input_example,
            auth_policy=AuthPolicy(
                system_auth_policy=system_auth_policy,
                user_auth_policy=user_auth_policy,
            ),
        )
        print(f"Model logged: {uc_model_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 10: Deploy (run manually)
# MAGIC
# MAGIC Gated by `DEPLOY_V3=1` env var (same gate as Cell 9).

# COMMAND ----------

# Guard: skip during log_model validation
if _deploy_enabled() and not mlflow.active_run():
    from databricks import agents
    from mlflow.tracking import MlflowClient
    from mlflow.deployments import get_deploy_client

    uc_model_name = _resolve_uc_model_name()
    endpoint_name = _resolve_endpoint_name()

    # --- Configurable scale-out ---
    # Small (1-4), Medium (8-16), Large (16-64)
    WORKLOAD_SIZE = os.environ.get(
        "SERVING_WORKLOAD_SIZE",
        _CFG.get("serving", {}).get("workload_size", "Large"),
    )
    SCALE_TO_ZERO = os.environ.get(
        "SERVING_SCALE_TO_ZERO",
        str(_CFG.get("serving", {}).get("scale_to_zero", False)),
    ).lower() == "true"

    client = MlflowClient()
    versions = client.search_model_versions(f"name='{uc_model_name}'")
    latest_version = max(int(v.version) for v in versions) if versions else 1

    experiment_name = f"/Shared/{uc_model_name}_traces"
    mlflow.set_experiment(experiment_name)

    # SP credentials for the serving container's SP-side calls (episodic
    # memory writes, Vector Search reads, UC catalog list, Volume writes for
    # charts). Reads from the `agent-secrets` scope on this workspace —
    # secret keys: `sp-client-id` + `sp-client-secret`. The OBO migration
    # removes the previously-injected `DATABRICKS_TOKEN` so per-user tool
    # calls flow as the calling user via ModelServingUserCredentials() —
    # see the OBO dual-client pattern.
    try:
        _sp_client_id = dbutils.secrets.get("agent-secrets", "sp-client-id")  # noqa: F821
        _sp_client_secret = dbutils.secrets.get("agent-secrets", "sp-client-secret")  # noqa: F821
    except Exception as _sec_err:
        # Hackathon / Free Edition: agent-secrets scope is rarely configured.
        # Both v2 and v3 paths now fall back to DATABRICKS_TOKEN injection.
        # The SP-OAuth M2M path is a prod hardening, not a hackathon need.
        logger.warning(
            f"agent-secrets scope not available; falling back to DATABRICKS_TOKEN. "
            f"Original error: {_sec_err}"
        )
        _sp_client_id = ""
        _sp_client_secret = ""

    # Step 1: Deploy agent (creates endpoint if needed)
    _lakebase_url_for_deploy = _CFG.get("lakebase", {}).get("url", "")
    # MLflow trace experiment — `workspace_config.yml.mlflow.experiment_name`
    # points at the v2 experiment, so without an explicit override every v3
    # trace lands in the v2 experiment (which made the v3 Traces UI look
    # empty even though the agent was running fine — discovered 2026-04-29).
    # Pin the experiment per UC model name so each endpoint logs to its own.
    _exp_name = (
        f"/Shared/{uc_model_name}_traces"
        if _deploy_v3_enabled()
        else _CFG.get("mlflow", {}).get("experiment_name", "")
    )
    # APP_URL — same pattern. If workspace_config.yml's `app.name` points at a
    # different app, the derived URL would steer chart links to the wrong app
    # (e.g. "Open chart" from a chart rendered on this endpoint resolving to a
    # <prior-app-name> URL because render_chart emitted the other app's URL),
    # so we override it per endpoint.
    # Read the app name from config so the endpoint's chart / graph URLs point
    # at the parallel app for this build, not any production one.
    _v3_app_name = _APP_CFG.get("name") or "neo4j-skills-agent-ui"
    # Explicit app.url wins — _derive_app_url only knows the Azure URL shape
    # and returns None on AWS hosts (dbc-*.cloud.databricks.com), which would
    # silently drop APP_URL from the endpoint env.
    _v3_app_url = _APP_CFG.get("url") or _derive_app_url(DATABRICKS_HOST, _v3_app_name)
    _env_vars = {
        "ENABLE_MLFLOW_TRACING": "true",
        "MLFLOW_EXPERIMENT_NAME": _exp_name,
        "DATABRICKS_HOST": DATABRICKS_HOST,
        "LLM_ENDPOINT_NAME": LLM_ENDPOINT_NAME,
        "CLUSTER_ID": CLUSTER_ID,
        "SQL_WAREHOUSE_ID": SQL_WAREHOUSE_ID,
        "WORKSPACE_URL": WORKSPACE_URL,
        "SQL_WAREHOUSE_HTTP_PATH": f"/sql/1.0/warehouses/{SQL_WAREHOUSE_ID}",
        "USE_SERVERLESS_EXECUTION": "true",
        "GENIE_TIMEOUT_SECONDS": str(GENIE_TIMEOUT_SECONDS),
        "LAKEBASE_URL": _lakebase_url_for_deploy,
        # MLflow client-side HTTP timeout (default 120s). Raise to 300s
        # so the serving container's own MLflow client calls don't bail
        # before the 297s server-side cap. Paired with the Apps-side
        # heartbeat/resume fix — see the long-running-query timeout fix.
        "MLFLOW_HTTP_REQUEST_TIMEOUT": "300",
        # Episodic memory is removed for the hackathon build (module-level
        # EPISODIC_VS_ENABLED is hardcoded False and never reads this var).
        # Pinned "false" so `serving-endpoints get` shows the real state.
        "EPISODIC_VS_ENABLED": "false",
        # Langmem user-preferences hot-path. Pinned explicitly so the env
        # var shows up in `serving-endpoints get` without anyone having
        # to crack open the model artifact. Tool name in the model is
        # `save_user_preference`; reads happen automatically in
        # predict_stream via _retrieve_user_prefs(), no agent tool call.
        # See the user-preferences memory pattern.
        "USER_PREFS_ENABLED": "true" if USER_PREFS_ENABLED else "false",
        "USER_PREFS_NUM_RESULTS": str(USER_PREFS_NUM_RESULTS),
        # Neo4j skills-brain (find_skill). Query embedding endpoint + knobs.
        "BRAIN_EMBED_ENDPOINT": FIND_SKILL_EMBED_ENDPOINT,
        "BRAIN_EMBED_BACKEND": "databricks",
        "BRAIN_EMBED_DIM": "1024",
        "BRAIN_EMBED_BATCH": "1",  # Free-Edition gte endpoint caps inputs/request
        "FIND_SKILL_RESULT_K": str(FIND_SKILL_RESULT_K),
        "FIND_SKILL_RENDER_GRAPH": "true" if FIND_SKILL_RENDER_GRAPH else "false",
    }
    # Neo4j connection — SAP GraphRAG pattern: resolve from a secret scope at
    # runtime via {{secrets/scope/key}} refs (created by setup_neo4j_secrets.sh).
    # For a quick Free-Edition dry-run, set `neo4j.inject_plaintext: true` in
    # workspace_config.yml to inject the creds directly (like LAKEBASE_URL).
    _neo4j_deploy_cfg = _CFG.get("neo4j", {}) or {}
    _secrets_scope = (_CFG.get("secrets", {}) or {}).get("scope_name", "agent-secrets")
    if str(_neo4j_deploy_cfg.get("inject_plaintext", "false")).lower() == "true":
        for _ke, _kc in (("NEO4J_URI", "uri"), ("NEO4J_USER", "user"),
                         ("NEO4J_PASSWORD", "password"), ("NEO4J_DATABASE", "database")):
            if _neo4j_deploy_cfg.get(_kc):
                _env_vars[_ke] = str(_neo4j_deploy_cfg[_kc])
    else:
        _env_vars.update({
            "NEO4J_URI": f"{{{{secrets/{_secrets_scope}/neo4j-uri}}}}",
            "NEO4J_USER": f"{{{{secrets/{_secrets_scope}/neo4j-user}}}}",
            "NEO4J_PASSWORD": f"{{{{secrets/{_secrets_scope}/neo4j-password}}}}",
            "NEO4J_DATABASE": f"{{{{secrets/{_secrets_scope}/neo4j-database}}}}",
        })
    if _sp_client_id and _sp_client_secret:
        _env_vars["DATABRICKS_CLIENT_ID"] = _sp_client_id
        _env_vars["DATABRICKS_CLIENT_SECRET"] = _sp_client_secret
    elif DATABRICKS_TOKEN:
        # Hackathon / v2-legacy: inject deployer's PAT as fallback. Either v3
        # without SP creds OR v2 lands here. Without one of these the serving
        # container has no Databricks creds and SP-side tool calls all 401.
        _env_vars["DATABRICKS_TOKEN"] = DATABRICKS_TOKEN
    if _deploy_v3_enabled() and _v3_app_url:
        # Steers chart_url emission at render_chart toward this build's app so
        # the user's "Open chart" link doesn't resolve to a <prior-app-name> URL.
        _env_vars["APP_URL"] = _v3_app_url

    # Free Edition enforces a workspace-wide scale-to-zero policy on Model
    # Serving endpoints. agents.deploy() defaults to scale_to_zero=False on
    # older databricks-agents versions, which fails the policy check before
    # the endpoint is even created. Pass scale_to_zero_enabled explicitly,
    # falling back if the SDK rejects the kwarg.
    # databricks-agents uses `scale_to_zero` (snake_case, no _enabled) at the
    # SDK level. Free Edition enforces scale-to-zero=True workspace-wide, so
    # this kwarg has to be set at endpoint-create time — update_endpoint after
    # the fact is too late because endpoint creation fails first.
    _deploy_kwargs = dict(
        deploy_feedback_model=False,
        environment_vars=_env_vars,
        scale_to_zero=SCALE_TO_ZERO,
        workload_size=WORKLOAD_SIZE,
    )
    try:
        agents.deploy(uc_model_name, latest_version, **_deploy_kwargs)
    except TypeError as _tex:
        logger.warning(
            f"agents.deploy rejected scale_to_zero/workload_size kwargs: {_tex}. "
            "Retrying without — endpoint may not have scale-to-zero applied."
        )
        agents.deploy(
            uc_model_name,
            latest_version,
            deploy_feedback_model=False,
            environment_vars=_env_vars,
        )

    print(f"Deployed {uc_model_name} version {latest_version}")

    # --- Helper: wait for endpoint config_update to finish before next update ---
    def _wait_endpoint_ready(name: str, timeout_s: int = 1800):
        import time
        deploy_client_local = get_deploy_client("databricks")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                ep = deploy_client_local.get_endpoint(endpoint=name)
                state = (ep or {}).get("state", {}) if isinstance(ep, dict) else {}
                ready = state.get("ready", "") if isinstance(state, dict) else ""
                cfg = state.get("config_update", "") if isinstance(state, dict) else ""
                if str(ready).upper() in ("READY", "TRUE") and str(cfg).upper() in ("NOT_UPDATING", ""):
                    return True
            except Exception:
                pass
            time.sleep(15)
        return False

    deploy_client = get_deploy_client("databricks")

    # Step 2: Update scale-out configuration
    # CRITICAL: include environment_vars in this update — `update_endpoint`
    # *replaces* served_entities config wholesale, so a partial config that
    # omits env_vars wipes everything `agents.deploy(environment_vars=...)`
    # just set. Symptoms when missing: env_vars on the live endpoint show as
    # empty {} after deploy, the serving container falls through to v2-flavoured
    # defaults, and MLflow traces silently disappear.
    if WORKLOAD_SIZE != "Small" or not SCALE_TO_ZERO:
        print(f"\nUpdating endpoint scale-out: {WORKLOAD_SIZE}, scale_to_zero={SCALE_TO_ZERO}...")
        _wait_endpoint_ready(endpoint_name)
        try:
            deploy_client.update_endpoint(
                endpoint=endpoint_name,
                config={
                    "served_entities": [
                        {
                            "entity_name": uc_model_name,
                            "entity_version": str(latest_version),
                            "workload_size": WORKLOAD_SIZE,
                            "scale_to_zero_enabled": SCALE_TO_ZERO,
                            "environment_vars": _env_vars,
                        }
                    ],
                },
            )
            print(f"Scale-out updated: {WORKLOAD_SIZE} (scale_to_zero={SCALE_TO_ZERO})")
        except Exception as e:
            print(f"Scale-out update failed (update manually in UI): {e}")

    # Step 3 (v3 only): AI Gateway = inference tables + usage tracking in
    # one block. Single update_endpoint call because the prior two-call
    # variant flipped inference_table on but left usage_tracking_config
    # at enabled=false on the live config (probably a config-merge race
    # between the two sequential updates). The table_name_prefix is derived
    # from the config-driven UC model name so tables don't fragment.
    if _deploy_v3_enabled():
        print("\nEnabling AI Gateway (inference tables + usage tracking)...")
        _wait_endpoint_ready(endpoint_name)
        try:
            # Inference table catalog/schema/prefix derived from the config-driven
            # UC model name so this works across workspaces; never hardcode a UC catalog.
            _parts = uc_model_name.split(".")
            _it_catalog = _parts[0] if len(_parts) >= 1 else "main"
            _it_schema = _parts[1] if len(_parts) >= 2 else "default"
            _it_prefix = _parts[2] if len(_parts) >= 3 else "orchestrator_agent"
            deploy_client.update_endpoint(
                endpoint=endpoint_name,
                config={
                    "ai_gateway": {
                        "usage_tracking_config": {"enabled": True},
                        "inference_table_config": {
                            "catalog_name": _it_catalog,
                            "schema_name": _it_schema,
                            "table_name_prefix": _it_prefix,
                            "enabled": True,
                        },
                    },
                },
            )
            print("AI Gateway update submitted")
        except Exception as e:
            print(f"AI Gateway update failed (set manually in UI): {e}")

        # Verify the flip actually landed — re-read live config and warn
        # if usage_tracking didn't enable.
        _wait_endpoint_ready(endpoint_name)
        try:
            ep = deploy_client.get_endpoint(endpoint=endpoint_name) or {}
            gw = ep.get("ai_gateway", {}) if isinstance(ep, dict) else {}
            usage_on = (gw.get("usage_tracking_config", {}) or {}).get("enabled", False)
            inf_on = (gw.get("inference_table_config", {}) or {}).get("enabled", False)
            print(f"AI Gateway live state: usage_tracking={usage_on} inference_table={inf_on}")
            if not (usage_on and inf_on):
                print("WARNING: AI Gateway flip did not fully land — re-check via UI.")
        except Exception as e:
            print(f"AI Gateway verify failed: {e}")


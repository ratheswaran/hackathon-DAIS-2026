"""Model Serving tool-filter + failed-tool-pruning middlewares.

Allow-list of tools safe to expose to the Model Serving container.

**Added** analysis tools: ``describe_dataframe``, ``query_stored_dfs``,
``think_tool``, ``save_python_notebook``.

**Removed** legacy tools replaced by compact-ref equivalents:
``get_dataframe``, ``render_visualization``.

``FailedToolPruningMiddleware`` introduces no behavior change.
"""

from __future__ import annotations

import logging
from typing import Callable

from deepagents_framework.agent.agent_middleware import AgentMiddleware
from deepagents_framework.models.model_request import ModelRequest
from deepagents_framework.models.model_response import ModelResponse

logger = logging.getLogger(__name__)


class ModelServingToolFilterMiddleware(AgentMiddleware):
    """Whitelist tools safe for Model Serving containers.

    Tools not in ``ALLOWED_TOOLS`` are silently removed from the
    request before it reaches the LLM. This prevents model-hallucinated
    tool names or stale tool schemas from triggering execution errors
    on the serving container.
    """

    ALLOWED_TOOLS = {
        # Orchestrator data retrieval (direct)
        "ask_genie_space",
        "run_spark_sql",
        # v2 analysis + exploration
        "describe_dataframe",
        "query_stored_dfs",
        "think_tool",
        # Python execution
        "run_python_code",
        "run_python_notebook",
        "save_python_notebook",
        # Variable Store (shared across all agents)
        "store_dataframe",
        "list_dataframes",
        # Langmem hot-path user preferences (orchestrator-only write tool;
        # reads happen in predict_stream via _retrieve_user_prefs, no tool).
        "save_user_preference",
        # DeepAgent built-in (Store-backed)
        "write_todos",
        "read_todos",
        # DeepAgent built-in (routed to DatabricksVolumesBackend)
        "write_file",
        "read_file",
        "edit_file",
        "ls",
        "glob",
        "grep",
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
            logger.info("ToolFilter: removed %s", removed)
        return handler(request.override(tools=filtered_tools))


class FailedToolPruningMiddleware(AgentMiddleware):
    """Remove failed tool call + response pairs from message history.

    Keeps the most recent failed group as context (so the LLM can
    learn from the error), but strips older failed tool rounds to save
    tokens. Copied verbatim from v1.
    """

    _ERROR_KEYWORDS = ["error", "exception", "timed out", "not found", "failed"]

    def _is_error_response(self, content: str) -> bool:
        return any(kw in content.lower() for kw in self._ERROR_KEYWORDS)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        messages = list(request.messages)

        ai_tool_groups: list[tuple[int, list[int]]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_call_ids = {
                    tc["id"] if isinstance(tc, dict) else getattr(tc, "id", None)
                    for tc in msg.tool_calls
                }
                tool_response_indices: list[int] = []
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

        failed_indices: set[int] = set()
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
            for ai_idx, resp_indices in ai_tool_groups:
                if ai_idx == last_ai:
                    failed_indices.discard(ai_idx)
                    for ri in resp_indices:
                        failed_indices.discard(ri)
                    break

        if not failed_indices:
            return handler(request)

        logger.info("FailedToolPruning: removing %d messages", len(failed_indices))
        filtered = [m for i, m in enumerate(messages) if i not in failed_indices]
        return handler(request.override(messages=filtered))

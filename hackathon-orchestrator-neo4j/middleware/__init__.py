"""Middleware for the orchestrator_agent_v2 deploy.

- `tool_filter.ModelServingToolFilterMiddleware` — whitelists tools exposed
  through Model Serving (mirrors the v1 pattern, allow-list updated for new
  tools `describe_dataframe`, `query_stored_dfs`, `think_tool`, `render_chart`,
  `save_python_notebook`).
- `failed_tool_pruning.FailedToolPruningMiddleware` — removes failed tool
  call / result pairs from message history to prevent context pollution
  (copied verbatim from v1).
"""

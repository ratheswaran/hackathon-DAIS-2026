"""Describe a stored DataFrame (plan group A4).

Thin wrapper around ``LakebaseVariableStore.describe()``. Returns a
compact JSON payload containing schema, row_count, basic pandas stats,
and a 3-row sample. Together with ``query_stored_dfs`` this replaces
the v1 ``get_dataframe`` tool (plan A5: "do not copy") — the LLM no
longer pulls raw rows into context for exploration; it pulls a
describe summary instead and issues SQL queries against the actual
table via DuckDB-ATTACH-postgres.

Spec: ``deep_agent_ra_v2/plans/functional-dancing-tiger.md`` A4.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error

logger = logging.getLogger(__name__)


def build_describe_dataframe_tool(
    *,
    variable_store_cls: Any,
    stats_sample_size: int = 1000,
):
    """Build ``describe_dataframe`` with the VariableStore class bound.

    Args:
        variable_store_cls: Class whose ``(store, config)``-constructed
            instance exposes a ``describe(name, stats_sample_size=...)``
            method. ``LakebaseVariableStore`` is the production choice.
        stats_sample_size: Max rows to pull for pandas ``.describe()``.
            Larger = more accurate stats, slower.
    """

    @tool
    def describe_dataframe(
        name: str,
        config: RunnableConfig = None,
        store: Annotated[Any, InjectedStore()] = None,
    ) -> str:
        """Summarize a stored DataFrame without pulling raw rows.

        Call BEFORE ``query_stored_dfs`` / ``run_python_code`` to see the
        schema, row count, stats, and a small sample.

        Args:
            name: Variable name (from the auto-store ref or ``list_dataframes``).

        Returns:
            JSON ``{"status": "ok", variable_name, schema, row_count, stats,
            sample, source, description}`` or ``{"status": "error",
            "error_type": "not_found", ...}``.
        """
        if not name:
            return json.dumps(_compact_error("missing_name", "name is required."))

        try:
            vs = variable_store_cls(store, config or {})
            out = vs.describe(name, stats_sample_size=stats_sample_size)
        except Exception as e:
            logger.warning("describe_dataframe failed: %s", e)
            return json.dumps(_compact_error("describe_error", str(e)))

        if out is None:
            return json.dumps(
                _compact_error(
                    "not_found",
                    f"No stored DataFrame named '{name}'. Call list_dataframes to see what's available.",
                )
            )

        return json.dumps(out, default=str)

    return describe_dataframe

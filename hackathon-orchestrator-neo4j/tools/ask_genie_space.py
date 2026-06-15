"""PRIMARY Genie-first data retrieval tool (plan group A2).

Replaces the v1 ``ask_genie_space`` which returned a 50-row markdown table
dump plus SQL + interpretation + status as a multi-line string. The v2
version stores the result to the VariableStore and returns a compact
pass-by-reference payload via ``_compact_ref`` — keeping the tool return
under ~500 tokens even for multi-thousand-row query results.

**What was stripped** (v1 source lines 1116-1135 of
``deep_agent_ra/deploy_orchestrator_agent.py``):

- ``display_limit = 50`` row loop building a markdown table
- Header / separator construction
- "... N more rows truncated" tail

**What was kept:**

- Genie API call with configurable timeout
- ``_format_genie_response`` parsing (copied verbatim, with
  ``workspace_client`` moved from a module global to an explicit kwarg
  so the helper is unit-testable)
- Auto-store to the VariableStore via the injected ``store`` param
- Genie's natural-language interpretation (now mapped into
  ``_compact_ref.description``)

**Factory pattern:** unlike v1's module-global ``_workspace_client``, the
tool is built via ``build_ask_genie_space_tool(workspace_client=...,
variable_store_cls=...)`` — matching the subagent builder pattern in
``subagents/python_analyst.py`` and avoiding circular imports with the
deploy notebook. The factory closes over ``workspace_client`` and
``variable_store_cls`` so tests can inject fakes.

Spec: ``deep_agent_ra_v2/plans/functional-dancing-tiger.md`` A2 (ST §1.3).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import timedelta
from typing import Annotated, Any

import pandas as pd
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error, _compact_ref
# _sql_sanitizer dropped for hackathon — TH-agency-specific cleaners.
def apply_trim(sql: str) -> str:
    return sql
def ensure_region_filter(sql: str, question: str) -> str:
    return sql
from util.trace_collector import record_sql

logger = logging.getLogger(__name__)

# ── CONFIGURATION ────────────────────────────────────────────────────────
# When True, auto-apply TRIM() and mandatory region filters to Genie SQL.
# Disable via env var for experimental runs.
SQL_STRICT_MODE = os.environ.get("SQL_STRICT_MODE", "true").lower() == "true"


def _format_genie_response(
    question: str,
    genie_message: Any,
    space_id: str,
    *,
    workspace_client: Any,
) -> dict[str, Any]:
    """Format a Genie SDK response into a clean dict.

    Copied verbatim from v1 ``deep_agent_ra/deploy_orchestrator_agent.py``
    (``_format_genie_response`` at line 1002), with ``workspace_client``
    lifted from a module global to an explicit kwarg so the helper can
    be unit-tested with a fake client.
    """
    result: dict[str, Any] = {
        "question": question,
        "conversation_id": getattr(genie_message, "conversation_id", None),
        "message_id": getattr(genie_message, "id", None),
        "status": (
            str(genie_message.status.value)
            if getattr(genie_message, "status", None)
            else "UNKNOWN"
        ),
    }

    attachments = getattr(genie_message, "attachments", None) or []
    for attachment in attachments:
        query = getattr(attachment, "query", None)
        if query is not None:
            result["sql"] = getattr(query, "query", "") or ""
            result["description"] = getattr(query, "description", "") or ""

            meta = getattr(query, "query_result_metadata", None)
            if meta is not None:
                result["row_count"] = getattr(meta, "row_count", None)

            att_id = getattr(attachment, "attachment_id", None)
            if att_id:
                try:
                    data_result = workspace_client.genie.get_message_query_result_by_attachment(
                        space_id=space_id,
                        conversation_id=genie_message.conversation_id,
                        message_id=genie_message.id,
                        attachment_id=att_id,
                    )
                    sr = getattr(data_result, "statement_response", None)
                    if sr is not None:
                        manifest = getattr(sr, "manifest", None)
                        if (
                            manifest
                            and getattr(manifest, "schema", None)
                            and getattr(manifest.schema, "columns", None)
                        ):
                            result["columns"] = [c.name for c in manifest.schema.columns]
                        res = getattr(sr, "result", None)
                        if res and getattr(res, "data_array", None):
                            result["data"] = res.data_array
                except Exception as e:
                    logger.warning("Failed to fetch Genie query results: %s", e)

        text = getattr(attachment, "text", None)
        if text is not None:
            result["text_response"] = getattr(text, "content", "") or ""

    return result


# ── Post-query validation ────────────────────────────────────────────────
# DOMAIN CONFIG: golden facts are domain-specific. If you add a new domain,
# add its known-good values here. The mechanism (_validate_result) is generic.
_GOLDEN_FACTS: dict[tuple[str, str], int] = {
    ("active agents", "2021-01"): 13_746,
    ("inforce agents", "2021-03"): 55_950,
}


def _validate_result(question: str, df: pd.DataFrame) -> bool:
    """Log a warning if a known metric deviates from its golden value.

    Returns True if validation passed (or was not applicable), False if
    a deviation was detected.
    """
    qkey = question.lower()
    for (metric, month), expected in _GOLDEN_FACTS.items():
        if metric not in qkey:
            continue
        year, mth = month.split("-")
        if year not in qkey and month not in qkey:
            continue
        try:
            count_cols = [c for c in df.columns if "count" in c.lower() or "agent" in c.lower()]
            month_cols = [c for c in df.columns if "month" in c.lower() or "mth" in c.lower()]
            if not count_cols or not month_cols:
                continue
            month_col = month_cols[0]
            count_col = count_cols[0]
            mth_int = int(mth)
            mask = df[month_col].apply(lambda v: int(v) == mth_int if pd.notna(v) else False)
            if mask.any():
                actual = int(df.loc[mask, count_col].iloc[0])
                if actual != expected:
                    logger.warning(
                        "Golden-fact validation FAILED for '%s' %s: got %d, expected %d",
                        metric, month, actual, expected,
                    )
                    return False
        except Exception:
            pass
    return True


# DOMAIN CONFIG: expected ANP magnitude range for the default scope.
# Adjust these bounds when adding non-Thailand domains.
_ANP_EXPECTED_LOW = 0.8e9
_ANP_EXPECTED_HIGH = 1.2e9


def _sanity_check_anp(df: pd.DataFrame) -> None:
    """Warn if ANP values are outside the expected range (possible wrong series)."""
    anp_cols = [c for c in df.columns if "ANP" in c.upper()]
    for col in anp_cols:
        try:
            mean_val = pd.to_numeric(df[col], errors="coerce").mean()
            if pd.notna(mean_val) and mean_val > 1e6:
                if not (_ANP_EXPECTED_LOW <= mean_val <= _ANP_EXPECTED_HIGH):
                    logger.warning(
                        "ANP magnitude out of expected range: %.2e in column '%s' "
                        "(expected %.1e-%.1e). Possible wrong series.",
                        mean_val, col, _ANP_EXPECTED_LOW, _ANP_EXPECTED_HIGH,
                    )
        except Exception:
            pass


def build_ask_genie_space_tool(
    *,
    workspace_client: Any,
    variable_store_cls: Any,
    genie_timeout_seconds: int = 600,
):
    """Build the ``ask_genie_space`` tool with dependencies bound.

    The returned object is the ``@tool``-decorated function — pass it
    directly into the orchestrator's ``tools=[...]`` list.

    Args:
        workspace_client: A ``databricks.sdk.WorkspaceClient`` (or a
            test fake exposing ``.genie.start_conversation_and_wait``
            and ``.genie.get_message_query_result_by_attachment``).
        variable_store_cls: The ``VariableStore`` class. Must expose
            ``auto_name(question, space_id)`` (classmethod or
            staticmethod) and an instance method
            ``store(name, df, *, source, description, query_sql)``.
        genie_timeout_seconds: Passed to
            ``start_conversation_and_wait`` as ``timeout=timedelta(...)``.
    """

    @tool
    def ask_genie_space(
        space_id: str,
        question: str,
        config: RunnableConfig = None,
        store: Annotated[Any, InjectedStore()] = None,
    ) -> str:
        """Ask a natural-language question to a Genie Space; the result is auto-stored.

        PRIMARY data-retrieval tool. Genie writes and executes SQL from your
        question; the tool stores the result DataFrame and returns a COMPACT
        pass-by-reference JSON (variable_name, schema, row_count, preview_rows,
        columns, sql) so downstream tools (``query_stored_dfs``,
        ``describe_dataframe``) work on the full data without raw rows entering
        context. ``"was_overwritten": true`` means a same-named stored variable
        was replaced.

        STATELESS: every call starts a NEW Genie conversation — reformulate the
        FULL question each time, carrying forward every filter already
        established in the conversation.

        Get the space_id from the find_skill PLAN — never guess it.

        Args:
            space_id: Genie Space ID from the find_skill plan.
            question: A clear, specific natural-language question (metric,
                time period, grouping level).

        Returns:
            JSON string. On success: ``{"status": "ok", "variable_name",
            "source", "sql", "description", "schema", "row_count",
            "preview_rows", "columns"}``. On failure: ``{"status":
            "error", "error_type", "message", "sql"}``.
        """
        if not space_id:
            return json.dumps(
                _compact_error(
                    "missing_space_id",
                    "space_id is required. Call find_skill to get the routed Genie Space ID.",
                )
            )

        try:
            genie_message = workspace_client.genie.start_conversation_and_wait(
                space_id=space_id,
                content=question,
                timeout=timedelta(seconds=genie_timeout_seconds),
            )
        except TimeoutError:
            return json.dumps(
                _compact_error(
                    "genie_timeout",
                    f"Genie response timed out after {genie_timeout_seconds}s. "
                    f"The question may be too complex — try simplifying or breaking it into parts.",
                )
            )
        except Exception as e:
            return json.dumps(_compact_error("genie_error", str(e)))

        # Bare-name lookup so tests can monkeypatch
        # ``tools.ask_genie_space._format_genie_response``.
        response = _format_genie_response(
            question, genie_message, space_id, workspace_client=workspace_client
        )

        status = response.get("status", "UNKNOWN")
        if status not in ("COMPLETED", "EXECUTING_QUERY"):
            return json.dumps(
                _compact_error(
                    f"genie_status_{str(status).lower()}",
                    response.get("text_response")
                    or response.get("error")
                    or "Genie did not complete successfully",
                    sql=response.get("sql"),
                )
            )

        cols = response.get("columns")
        data = response.get("data")
        sql = response.get("sql")
        description = response.get("description") or None

        if not (cols and data):
            # Genie returned metadata only (no rows) — build an empty
            # DataFrame and still return a compact ref so the LLM sees
            # the schema and can decide how to recover.
            var_name = variable_store_cls.auto_name(question, space_id)
            return json.dumps(
                _compact_ref(
                    var_name=var_name,
                    source=f"genie:{space_id}",
                    sql=sql,
                    df=pd.DataFrame(columns=cols or []),
                    description=description,
                )
            )

        df = pd.DataFrame(data, columns=cols)
        var_name = variable_store_cls.auto_name(question, space_id)

        # ── SQL sanitisation (strict mode) ──────────────────────────
        if sql and SQL_STRICT_MODE:
            sql = apply_trim(sql)
            sql = ensure_region_filter(sql, question)

        # Record full SQL for episodic memory (before compact_ref truncates)
        if sql:
            record_sql(sql, source="genie")

        was_overwritten = False
        if store is not None:
            try:
                vs = variable_store_cls(store, config or {})
                vs.store(
                    var_name,
                    df,
                    source=f"genie:{space_id}",
                    description=description or question,
                    query_sql=sql or "",
                )
                was_overwritten = getattr(vs, "last_was_overwritten", False)
            except Exception as e:
                # Auto-store failure does NOT block the tool return —
                # the LLM still gets a compact ref and can re-store
                # explicitly if it needs to.
                logger.warning("VariableStore.store failed: %s", e)

        # ── Post-query validation (warn-only, never blocks) ─────────
        _validate_result(question, df)
        _sanity_check_anp(df)

        return json.dumps(
            _compact_ref(
                var_name=var_name,
                source=f"genie:{space_id}",
                sql=sql,
                df=df,
                description=description,
                was_overwritten=was_overwritten,
            )
        )

    return ask_genie_space

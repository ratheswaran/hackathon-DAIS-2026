"""Per-request trace collector for SQL queries executed by tools.

Any tool — whether running in the orchestrator or inside a subagent —
can record its SQL query here. The orchestrator drains the collector
once after the stream loop to populate the episodic-memory table.

## Why ContextVar, not a module-level list

This code runs inside Databricks Model Serving, which handles many
concurrent ``predict_stream`` invocations on the same process (workload
size ``Large`` = 16-64 concurrent). Earlier this collector used a
module-global ``list[str]`` guarded by a ``threading.Lock``. The lock
gives atomicity for individual append/drain calls, but does nothing to
isolate records across requests: tools for requests A and B both append
to the same shared buffer, and whichever request drains first in
``predict_stream`` gets *everyone's* SQL. That SQL is then stored in the
draining user's episodic-memory Delta row and re-injected into future
prompts via ``recall_past_analysis`` — a cross-tenant privacy leak into
persistent storage.

``contextvars.ContextVar`` is designed exactly for this case.
``asyncio`` propagates the current Context through awaits, and LangGraph
propagates it across thread-pool-dispatched tool workers via
``copy_context`` — so each request worker sees the parent request's
buffer rather than a shared global. ``threading.local`` *doesn't* work
here because LangGraph dispatches tool calls on thread-pool workers —
the tool thread is not the orchestrator's thread.

## Contract

``predict_stream`` must call ``start_trace()`` at the top of each
per-request block (before ``agent.stream()``) so the request gets its
own fresh list. Tools call ``record_sql(...)`` from anywhere. The
orchestrator calls ``drain()`` once after the stream completes.
"""

from __future__ import annotations

import contextvars
import logging

logger = logging.getLogger(__name__)

_queries_var: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "trace_collector_queries", default=None,
)


def start_trace() -> None:
    """Reset the per-request trace buffer. Call at the top of each
    ``predict_stream`` invocation before ``agent.stream()`` runs."""
    logger.info("[trace_collector] start_trace() called — buffer reset")
    _queries_var.set([])


def record_sql(sql: str, *, source: str = "") -> None:
    """Record a SQL query executed by any tool.

    Args:
        sql: The full, untruncated SQL statement.
        source: Optional label (``"spark_sql"``, ``"genie"``, etc.).
    """
    if not sql:
        return
    buf = _queries_var.get()
    if buf is None:
        # No start_trace() was called — lazily create a buffer rather
        # than drop the record. In production this is a bug (orchestrator
        # should always start the trace), but silently losing SQL makes
        # it harder to diagnose than keeping a degraded-but-visible trace.
        logger.warning(f"[trace_collector] record_sql called but buffer is None (start_trace not called). source={source}")
        buf = []
        _queries_var.set(buf)
    buf.append(sql)
    logger.info(f"[trace_collector] record_sql: source={source}, buf_len={len(buf)}, sql_preview={sql[:120]!r}")


def drain() -> list[str]:
    """Return all recorded queries for the current request and clear
    the buffer. Called once by the orchestrator after ``agent.stream()``
    finishes."""
    buf = _queries_var.get()
    logger.info(f"[trace_collector] drain() called — buf={'None' if buf is None else len(buf)} queries")
    if buf is None:
        return []
    out = list(buf)
    _queries_var.set([])
    logger.info(f"[trace_collector] drain() returning {len(out)} queries")
    return out

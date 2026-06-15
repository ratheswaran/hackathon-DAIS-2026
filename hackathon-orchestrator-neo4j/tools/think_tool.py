"""Scratch-pad reasoning tool for subagents (plan group A10).

A no-op tool whose only job is to give the LLM a slot in its tool-call
trajectory to write down its reasoning before picking a "real" tool.
The returned string is discarded by the orchestrator — the value is
entirely in the fact that the LLM was forced to emit structured
reflection as a tool call, which is visible to the next step of the
agent loop.

Pattern (wired into ``PYTHON_ANALYST_PROMPT`` and ``DATA_VIZ_PROMPT`` in
plan group B4):

    Before executing a primary tool, call ``think_tool`` with:
      1. Is the instruction explicit enough to execute?
      2. If not, what's the minimal analysis needed?
      3. Which tool is right for this step?

Origin: TUT §9 (Anthropic multi-step agent tutorial) + USER.
Spec: ``deep_agent_ra_v2/plans/functional-dancing-tiger.md`` A10.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def think_tool(reflection: str) -> str:
    """Scratch-pad — record reasoning as a visible step in the trajectory.

    Use only when a result genuinely surprises you (unexpected tool error,
    contradictory data): note the goal, the minimal interpretation, and the
    next tool + inputs. Never call it routinely.

    Args:
        reflection: Free-text reasoning.

    Returns:
        The reflection echoed back.
    """
    return f"Reflection recorded: {reflection}"

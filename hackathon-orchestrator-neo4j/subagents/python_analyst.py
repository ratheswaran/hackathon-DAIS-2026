"""python-analyst subagent builder.

Provides two construction paths:

1. **Dict-based** (preferred): ``build_python_analyst_subagent_dict()``
   returns a plain dict that ``create_deep_agent(subagents=[...])`` consumes
   directly.  This path supports ``skills=`` for per-subagent skill scoping
   (B5) — ``create_agent()`` does NOT accept ``skills``, but ``create_deep_agent``
   handles it when processing dict-based subagent definitions.

2. **CompiledSubAgent** (legacy): ``build_python_analyst_graph()`` +
   ``build_python_analyst_subagent()`` for cases where you need the raw
   compiled graph (e.g. unit tests). Does NOT support ``skills``.
"""

from typing import Any, Sequence

from langchain.agents import create_agent
from deepagents import CompiledSubAgent

PYTHON_ANALYST_NAME = "python-analyst"

PYTHON_ANALYST_DESCRIPTION = (
    "Performs statistical analysis, time series, correlations, merges, "
    "and transformations on data already in the Variable Store. Use when "
    "the question requires computation beyond what SQL provides."
)


def build_python_analyst_subagent_dict(
    *,
    tools: Sequence[Any],
    system_prompt: str,
    skills: Sequence[str] | None = None,
    model: Any = None,
    name: str = PYTHON_ANALYST_NAME,
    description: str = PYTHON_ANALYST_DESCRIPTION,
) -> dict:
    """Build a dict-based subagent definition for ``create_deep_agent``.

    This is the preferred path — dict subagents support ``skills=`` for
    per-subagent skill scoping, and ``create_deep_agent`` handles store
    propagation automatically. Pass ``model`` to override the orchestrator's
    model (e.g. use a cheaper/faster model for subagent work).
    """
    d: dict[str, Any] = {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "tools": list(tools),
    }
    if skills is not None:
        d["skills"] = list(skills)
    if model is not None:
        d["model"] = model
    return d


def build_python_analyst_graph(
    *,
    model: Any,
    store: Any,
    tools: Sequence[Any],
    system_prompt: str,
    name: str = PYTHON_ANALYST_NAME,
) -> Any:
    """Compile the python-analyst graph (legacy path).

    Passes ``store`` explicitly so ``InjectedStore()`` inside the analyst's
    tools resolves to the orchestrator's VariableStore. Does NOT support
    ``skills`` — use ``build_python_analyst_subagent_dict`` instead.
    """
    return create_agent(
        model,
        system_prompt=system_prompt,
        tools=list(tools),
        store=store,
        name=name,
    )


def build_python_analyst_subagent(
    graph: Any,
    *,
    name: str = PYTHON_ANALYST_NAME,
    description: str = PYTHON_ANALYST_DESCRIPTION,
) -> CompiledSubAgent:
    """Wrap the compiled graph in a CompiledSubAgent (legacy path)."""
    return CompiledSubAgent(
        name=name,
        description=description,
        runnable=graph,
    )

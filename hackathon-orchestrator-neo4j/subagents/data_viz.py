"""data-viz subagent builder.

Parallel to python_analyst.py. Two construction paths:

1. **Dict-based** (preferred): ``build_data_viz_subagent_dict()`` — supports
   ``skills=`` for per-subagent skill scoping via ``create_deep_agent``.

2. **CompiledSubAgent** (legacy): ``build_data_viz_graph()`` +
   ``build_data_viz_subagent()`` — for unit tests / raw graph access.
"""

from typing import Any, Sequence

from langchain.agents import create_agent
from deepagents import CompiledSubAgent

DATA_VIZ_NAME = "data-viz"

DATA_VIZ_DESCRIPTION = (
    "Creates D3 data-story infographics and scroll-driven narrative essays "
    "from data in the Variable Store (compose_infographic scene engine + "
    "compose_story scrollytelling). Use for multi-dataset / multi-scene "
    "stories and dashboard-style briefings."
)


def build_data_viz_subagent_dict(
    *,
    tools: Sequence[Any],
    system_prompt: str,
    skills: Sequence[str] | None = None,
    model: Any = None,
    name: str = DATA_VIZ_NAME,
    description: str = DATA_VIZ_DESCRIPTION,
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


def build_data_viz_graph(
    *,
    model: Any,
    store: Any,
    tools: Sequence[Any],
    system_prompt: str,
    name: str = DATA_VIZ_NAME,
) -> Any:
    """Compile the data-viz graph (legacy path, no skills support)."""
    return create_agent(
        model,
        system_prompt=system_prompt,
        tools=list(tools),
        store=store,
        name=name,
    )


def build_data_viz_subagent(
    graph: Any,
    *,
    name: str = DATA_VIZ_NAME,
    description: str = DATA_VIZ_DESCRIPTION,
) -> CompiledSubAgent:
    """Wrap the compiled graph in a CompiledSubAgent (legacy path)."""
    return CompiledSubAgent(
        name=name,
        description=description,
        runnable=graph,
    )

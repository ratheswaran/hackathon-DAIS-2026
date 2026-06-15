"""Subagent builders for the orchestrator_agent_v2 deploy.

Each submodule exports three construction paths:

1. **Dict-based** (preferred): ``build_<name>_subagent_dict(tools, prompt,
   skills)`` returns a plain dict for ``create_deep_agent(subagents=[...])``.
   Supports ``skills=`` for per-subagent skill scoping (B5).

2. **CompiledSubAgent** (legacy): ``build_<name>_graph()`` +
   ``build_<name>_subagent()`` for unit tests or raw graph access.
   Does NOT support ``skills``.

``prompts.py`` holds the system-prompt templates and the factory functions
that bind runtime values via str.format().
"""

from .prompts import (
    ORCHESTRATOR_PROMPT_TEMPLATE,
    PYTHON_ANALYST_PROMPT_TEMPLATE,
    DATA_VIZ_PROMPT_TEMPLATE,
    build_orchestrator_prompt,
    build_python_analyst_prompt,
    build_data_viz_prompt,
)
from .python_analyst import (
    PYTHON_ANALYST_NAME,
    PYTHON_ANALYST_DESCRIPTION,
    build_python_analyst_subagent_dict,
    build_python_analyst_graph,
    build_python_analyst_subagent,
)
from .data_viz import (
    DATA_VIZ_NAME,
    DATA_VIZ_DESCRIPTION,
    build_data_viz_subagent_dict,
    build_data_viz_graph,
    build_data_viz_subagent,
)

__all__ = [
    # Prompt templates + factories
    "ORCHESTRATOR_PROMPT_TEMPLATE",
    "PYTHON_ANALYST_PROMPT_TEMPLATE",
    "DATA_VIZ_PROMPT_TEMPLATE",
    "build_orchestrator_prompt",
    "build_python_analyst_prompt",
    "build_data_viz_prompt",
    # python-analyst
    "PYTHON_ANALYST_NAME",
    "PYTHON_ANALYST_DESCRIPTION",
    "build_python_analyst_subagent_dict",
    "build_python_analyst_graph",
    "build_python_analyst_subagent",
    # data-viz
    "DATA_VIZ_NAME",
    "DATA_VIZ_DESCRIPTION",
    "build_data_viz_subagent_dict",
    "build_data_viz_graph",
    "build_data_viz_subagent",
]

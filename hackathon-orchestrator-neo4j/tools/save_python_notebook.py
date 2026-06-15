"""Save-only notebook tool (plan group B2, first half).

Split from the v1 ``run_python_notebook`` which combined save + execute
in a single tool. ``save_python_notebook`` writes code to a Databricks
Workspace notebook and returns the URL — no execution, <1s. The user
gets a shareable, re-runnable artifact immediately.

The preamble is injected so the notebook is self-contained — users can
open it and Run All without missing ``variable_store`` or ``psycopg``.

Execution is handled by the sibling ``run_python_notebook`` tool, which
saves to an ephemeral ``_ephemeral/`` subdirectory and runs via the
Jobs API.

Spec: ``deep_agent_ra_v2/plans/functional-dancing-tiger.md`` B2.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Callable, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

from tools.compact_ref import _compact_error


def build_save_python_notebook_tool(
    *,
    save_fn: Callable[[str, str, str], Tuple[str, str]],
    build_preamble_fn: Callable[[Any], str] | None = None,
    variable_store_cls: Any = None,
):
    """Build the ``save_python_notebook`` tool.

    Args:
        save_fn: A callable ``(code, name, description) -> (notebook_path,
            notebook_url)`` that writes the code to Workspace. In production
            this is ``_save_notebook_to_workspace`` from the deploy notebook.
        build_preamble_fn: Optional callable to generate the variable_store
            preamble. When provided, saved notebooks are self-contained.
        variable_store_cls: VariableStore class for building the preamble proxy.
    """

    @tool
    def save_python_notebook(
        code: str,
        name: str,
        description: str = "Agent-generated analysis",
        config: RunnableConfig = None,
        store: Annotated[Any, InjectedStore()] = None,
    ) -> str:
        """Save Python/PySpark code as a Databricks notebook (no execution).

        Creates a shareable, re-runnable notebook in the Workspace at
        ``/Workspace/Users/<you>/agent_generated/<name>``. Returns the
        notebook URL so you can share it with the user.

        The saved notebook includes a variable_store preamble so it can
        be re-run manually — ``variable_store.get()``/``.store()`` will
        connect directly to Lakebase.

        Use this when the user asks to "save", "share", "keep", or make
        a notebook "reusable". For execution, use ``run_python_notebook``
        or ``run_python_code`` instead.

        Args:
            code: Complete Python/PySpark code.
            name: Short snake_case name (becomes the notebook filename).
            description: Brief description shown in the notebook header.

        Returns:
            JSON string with ``{status, path, url}`` on success, or a
            compact error payload on failure.
        """
        if not code or not code.strip():
            return json.dumps(_compact_error("empty_code", "Code is empty."))
        if not name or not name.strip():
            return json.dumps(_compact_error("empty_name", "Notebook name is required."))

        # Inject variable_store preamble so the notebook is self-contained
        full_code = code
        if build_preamble_fn and variable_store_cls and store is not None:
            try:
                proxy = variable_store_cls(store, config or {})
                preamble = build_preamble_fn(proxy)
                if preamble:
                    full_code = preamble + code
            except Exception:
                pass  # Fall back to raw code if preamble fails

        try:
            notebook_path, notebook_url = save_fn(full_code, name.strip(), description)
        except Exception as e:
            return json.dumps(_compact_error("save_failed", str(e)))

        if "(save failed" in str(notebook_url):
            return json.dumps(_compact_error("save_failed", notebook_url))

        return json.dumps({
            "status": "ok",
            "path": notebook_path,
            "url": notebook_url,
        })

    return save_python_notebook

"""Ephemeral notebook execution tool.

Auto-names notebooks under ``agent_generated/_ephemeral/`` and always
executes via the serverless Jobs API. The notebook is a transient
artifact — the user doesn't see it unless they go looking for it.

For saving shareable notebooks, use ``save_python_notebook`` instead.

Injects the VariableStore preamble + writeback parsing so
``variable_store.get()``/``.store()`` work inside the remote
execution context.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any, Callable, Optional, Tuple

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore

logger = logging.getLogger(__name__)


def build_run_python_notebook_tool(
    *,
    save_fn: Callable[[str, str, str], Tuple[str, str]],
    execute_fn: Callable[[str], str],
    build_preamble_fn: Callable[[Any], str],
    parse_writebacks_fn: Callable[[str, Any], Tuple[str, list]],
    variable_store_cls: Any,
    vs_sentinel: str = "__VS_STORE__:",
):
    """Build the ``run_python_notebook`` tool for ephemeral execution.

    Args:
        save_fn: ``(code, name, description) -> (path, url)`` — saves the
            notebook to Workspace. In production: ``_save_notebook_to_workspace``.
        execute_fn: ``(notebook_path) -> output_str`` — runs the saved
            notebook via serverless Jobs API. In production: ``_execute_serverless``.
        build_preamble_fn: ``(variable_store_proxy) -> preamble_code`` — injects
            VariableStore into the remote execution context.
        parse_writebacks_fn: ``(output, proxy) -> (cleaned_output, stored_names)``
            — parses ``__VS_STORE__:`` sentinel lines from stdout.
        variable_store_cls: VariableStore class (``LakebaseVariableStore``).
        vs_sentinel: The sentinel prefix for writeback lines in stdout.
    """

    @tool
    def run_python_notebook(
        code: str,
        name: str = "ephemeral",
        config: RunnableConfig = None,
        store: Annotated[Any, InjectedStore()] = None,
    ) -> str:
        """Execute Python/PySpark code on serverless compute.

        Runs the code as a Databricks notebook via the Jobs API. The
        notebook is auto-saved to ``agent_generated/_ephemeral/<name>_<ts>``
        — it's a transient artifact, not user-facing.

        A ``variable_store`` object is automatically injected:
        - ``variable_store.get("name")`` — load a stored DataFrame
        - ``variable_store.store("name", df)`` — save a DataFrame
        - ``variable_store.list_all()`` — list available data

        **Use this when you need:**
        - PySpark (distributed processing)
        - Packages not available in-process (scikit-learn, statsmodels)
        - Long-running computations that need serverless isolation

        For most analysis, prefer ``run_python_code`` (50-100x faster).
        For saving a shareable notebook, use ``save_python_notebook``.

        Args:
            code: Complete Python code. Has spark, pandas, numpy.
                End with ``dbutils.notebook.exit("result")`` to capture output.
            name: Short name for the ephemeral notebook.

        Returns:
            Execution output as a string. If the code stored DataFrames
            via ``variable_store.store()``, their names are appended.
        """
        if not code or not code.strip():
            return "Error: code is empty."

        # Build VariableStore preamble for remote execution
        proxy = variable_store_cls(store, config or {}) if store is not None else None
        preamble = build_preamble_fn(proxy) if proxy else ""
        full_code = preamble + code

        # Save as ephemeral notebook (needed for serverless execution path)
        ts = int(time.time())
        ephemeral_name = f"_ephemeral/{name.strip()}_{ts}"
        try:
            notebook_path, notebook_url = save_fn(full_code, ephemeral_name, f"Ephemeral: {name}")
        except Exception as e:
            return f"Error saving ephemeral notebook: {e}"

        if "(save failed" in str(notebook_url):
            return f"Error saving ephemeral notebook: {notebook_url}"

        # Execute via serverless
        try:
            exec_output = execute_fn(notebook_path)
        except Exception as e:
            return f"Serverless execution error: {e}"

        # Parse VariableStore writebacks
        if proxy and vs_sentinel in str(exec_output):
            exec_output, stored_names = parse_writebacks_fn(str(exec_output), proxy)
            if stored_names:
                exec_output += f"\n\nStored to variable store: {', '.join(stored_names)}"

        result = f"Execution output:\n{exec_output}"
        if notebook_url and "(save failed" not in str(notebook_url):
            result += f"\n\nNotebook: {notebook_url}"
        return result

    return run_python_notebook

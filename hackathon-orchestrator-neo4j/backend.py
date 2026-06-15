"""DatabricksVolumesBackend — Custom BackendProtocol for DeepAgents.

Maps DeepAgents' built-in file tools (write_file, read_file, ls, glob, grep)
to Databricks SDK operations:
- Text/artifacts → Unity Catalog Volumes (/Volumes/...)
- DataFrames → Delta scratch tables (configured via workspace_config.yml)
- Audit log → audit log Delta table (configured via workspace_config.yml)

Setup: Run setup_agent_fs_log.py first to create the audit log table.
Configuration: workspace_config.yml in project root (env vars override).
"""

import os
import io
import re
import json
import fnmatch
import logging
from pathlib import PurePosixPath

from databricks.sdk import WorkspaceClient
from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
    GrepMatch,
    WriteResult,
)

logger = logging.getLogger(__name__)

# ── SQL strict mode: auto-apply TRIM() and mandatory predicates to Genie SQL.
# Set SQL_STRICT_MODE=false to disable (e.g. for experimental runs).
SQL_STRICT_MODE = os.environ.get("SQL_STRICT_MODE", "true").lower() == "true"


def _load_workspace_config():
    """Load workspace_config.yml — search common locations."""
    import yaml
    from pathlib import Path
    for candidate in [
        Path("workspace_config.yml"),
        Path(__file__).parent / "workspace_config.yml",
    ]:
        if candidate and candidate.exists():
            with open(candidate) as f:
                return yaml.safe_load(f)
    return {}


_CFG = _load_workspace_config()

VOLUME_BASE = os.environ.get(
    "AGENT_VOLUME_PATH",
    _CFG.get("agent", {}).get("volume_path", "/Volumes/smart_claims/ai_ops/agent_scratch"),
)
SCRATCH_SCHEMA = os.environ.get(
    "AGENT_SCRATCH_SCHEMA",
    _CFG.get("agent", {}).get("scratch_schema", "smart_claims.ai_ops"),
)
AUDIT_LOG_TABLE = os.environ.get(
    "AGENT_AUDIT_LOG_TABLE",
    _CFG.get("agent", {}).get("audit_log_table", "smart_claims.ai_ops.agent_fs_log"),
)
SQL_WAREHOUSE_ID = os.environ.get(
    "SQL_WAREHOUSE_ID",
    _CFG.get("compute", {}).get("sql_warehouse_id", "a75fe9905aae2120"),
)

# Lakebase Postgres — the /tables/ virtual FS now routes here per the
# 2026-05-13 hackathon decisions doc. Two schemas matter:
#   - ai_chatbot.scratch_* — orchestrator scratch tables (writeable)
#   - unhcr.*              — bronze-layer UNHCR data tables (read-only mirror of UC Delta)
LAKEBASE_URL = os.environ.get(
    "LAKEBASE_URL", _CFG.get("lakebase", {}).get("url", "")
)
LAKEBASE_SCRATCH_SCHEMA = os.environ.get(
    "LAKEBASE_SCRATCH_SCHEMA",
    _CFG.get("lakebase", {}).get("scratch_schema", "ai_chatbot"),
)


class DatabricksVolumesBackend(BackendProtocol):
    """BackendProtocol backed by Unity Catalog Volumes + Delta tables.

    File operations map to:
    - write_file/read_file → Volumes via w.files.upload/download
    - write_file("/notebooks/...") → Workspace notebooks via workspace.upload
    - ls/glob → Volumes via w.files.list_directory_contents
    - grep → Download + search in-memory

    Every operation is logged to the audit Delta table.
    """

    def __init__(
        self,
        workspace_client=None,
        volume_base=VOLUME_BASE,
        scratch_schema=SCRATCH_SCHEMA,
        audit_log_table=AUDIT_LOG_TABLE,
        sql_warehouse_id=SQL_WAREHOUSE_ID,
        cluster_id=None,
        thread_id=None,
        agent_name="spark-sql-agent",
        lakebase_url=LAKEBASE_URL,
        lakebase_scratch_schema=LAKEBASE_SCRATCH_SCHEMA,
    ):
        self._w = workspace_client or WorkspaceClient()
        self._volume_base = volume_base.rstrip("/")
        self._scratch_schema = scratch_schema
        self._audit_log_table = audit_log_table
        self._sql_warehouse_id = sql_warehouse_id
        self._cluster_id = cluster_id
        self._thread_id = thread_id
        self._agent_name = agent_name
        # Lakebase wiring for /tables/ virtual FS (hackathon Wave 3).
        self._lakebase_url = lakebase_url
        self._lakebase_scratch_schema = lakebase_scratch_schema
        self._pg_pool = None  # lazy psycopg_pool.ConnectionPool
        self._notebook_base = None  # set lazily from current user

        try:
            self._w.files.get_directory_metadata(self._volume_base)
        except Exception:
            try:
                self._w.files.create_directory(self._volume_base)
            except Exception as e:
                logger.warning(f"Could not create volume dir {self._volume_base}: {e}")

    _NOTEBOOK_EXTENSIONS = (".py", ".ipynb")
    _NOTEBOOK_KEYWORDS = ("notebook", "analysis", "pipeline", "etl", "transform")

    # ── Lakebase /tables/ virtual FS helpers (hackathon Wave 3) ───────────

    def _pg_connection(self):
        """Lazily-built Lakebase connection pool. Returns a psycopg connection
        from the pool — caller is responsible for `with` or close.

        Uses psycopg_pool.ConnectionPool with max_lifetime=600 / max_idle=120
        to survive Lakebase TCP-drop on idle (same lesson as v3 PostgresSaver).
        """
        if not self._lakebase_url:
            raise RuntimeError(
                "Lakebase URL not configured. Set LAKEBASE_URL env or "
                "lakebase.url in workspace_config.yml."
            )
        if self._pg_pool is None:
            import psycopg
            import psycopg_pool

            def _check(c):
                with c.cursor() as cur:
                    cur.execute("SELECT 1")

            self._pg_pool = psycopg_pool.ConnectionPool(
                self._lakebase_url,
                min_size=1, max_size=4,
                max_lifetime=600, max_idle=120,
                check=_check,
                kwargs={"autocommit": False},
            )
        return self._pg_pool.connection()

    def _parse_tables_path(self, file_path):
        """Map a `/tables/...` virtual path to a (schema, table) tuple.

        Supported forms:
          /tables/foo            → (scratch_schema_default, "foo")
          /tables/unhcr/foo      → ("unhcr", "foo")
          /tables/unhcr.foo      → ("unhcr", "foo")
        """
        rest = file_path.split("/tables/", 1)[1].strip("/")
        if "/" in rest:
            schema, table = rest.split("/", 1)
        elif "." in rest:
            schema, table = rest.split(".", 1)
        else:
            schema, table = self._lakebase_scratch_schema, rest
        return schema, table

    def _is_notebook_path(self, virtual_path):
        """Check if path targets the /notebooks/ virtual directory."""
        return virtual_path.lstrip("/").startswith("notebooks/") or virtual_path == "/notebooks"

    def _looks_like_notebook(self, file_path, content=""):
        """Detect if a write should be routed to Workspace as a notebook.

        Returns True if:
        - Path is under /notebooks/
        - Filename contains 'notebook' or similar keywords
        - Content starts with Databricks notebook header
        - File is .ipynb (JSON notebook format)
        """
        if self._is_notebook_path(file_path):
            return True

        name = PurePosixPath(file_path).name.lower()

        # .ipynb files → always route to Workspace as proper notebooks
        if name.endswith(".ipynb"):
            return True

        # Filename contains notebook-like keywords + is a .py file
        if name.endswith(".py") and any(kw in name for kw in self._NOTEBOOK_KEYWORDS):
            return True

        # Content starts with Databricks notebook header
        if content and content.lstrip().startswith("# Databricks notebook source"):
            return True

        return False

    def _get_notebook_base(self):
        """Resolve the Workspace notebook directory (lazy, cached)."""
        if self._notebook_base is None:
            try:
                user = self._w.current_user.me().user_name
                self._notebook_base = f"/Workspace/Users/{user}/agent_generated"
                try:
                    self._w.workspace.mkdirs(self._notebook_base)
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Could not resolve notebook base: {e}")
                self._notebook_base = "/Workspace/Users/unknown/agent_generated"
        return self._notebook_base

    def _resolve_notebook_path(self, virtual_path):
        """Map /notebooks/<name> → /Workspace/Users/<user>/agent_generated/<name>."""
        name = virtual_path.lstrip("/").removeprefix("notebooks/").lstrip("/")
        # Strip .py/.ipynb extensions — Databricks notebooks don't use them
        for ext in (".py", ".ipynb"):
            if name.endswith(ext):
                name = name[: -len(ext)]
        return f"{self._get_notebook_base()}/{name}"

    def _resolve_path(self, virtual_path):
        clean = virtual_path.lstrip("/")
        return f"{self._volume_base}/{clean}"

    def _log_operation(
        self, operation, path, storage_type="volume", physical_path=None,
        size_bytes=None, row_count=None, status="success", error_message=None,
        metadata=None,
    ):
        try:
            def esc(s):
                return s.replace("'", "''") if s else None

            cols = ["operation", "path", "storage_type", "status", "agent_name"]
            vals = [
                f"'{esc(operation)}'",
                f"'{esc(path)}'",
                f"'{esc(storage_type)}'",
                f"'{esc(status)}'",
                f"'{esc(self._agent_name)}'",
            ]

            if physical_path:
                cols.append("physical_path")
                vals.append(f"'{esc(physical_path)}'")
            if self._thread_id:
                cols.append("thread_id")
                vals.append(f"'{esc(self._thread_id)}'")
            if size_bytes is not None:
                cols.append("size_bytes")
                vals.append(str(size_bytes))
            if row_count is not None:
                cols.append("row_count")
                vals.append(str(row_count))
            if error_message:
                cols.append("error_message")
                vals.append(f"'{esc(error_message[:1000])}'")
            if metadata:
                cols.append("metadata_json")
                vals.append(f"'{esc(json.dumps(metadata, default=str))}'")

            sql = f"INSERT INTO {self._audit_log_table} ({', '.join(cols)}) VALUES ({', '.join(vals)})"
            self._w.statement_execution.execute_statement(
                warehouse_id=self._sql_warehouse_id, statement=sql, wait_timeout="30s",
            )
        except Exception as e:
            logger.warning(f"Failed to log operation to audit table: {e}")

    # --- ls_info ---

    def ls_info(self, path="/"):
        # Route /notebooks/ listing to Workspace
        if self._is_notebook_path(path):
            return self._ls_notebooks(path)

        physical = self._resolve_path(path)
        results = []

        try:
            for entry in self._w.files.list_directory_contents(physical):
                name = entry.name or ""
                entry_path = f"{path.rstrip('/')}/{name}" if path != "/" else f"/{name}"
                info = {"path": entry_path}
                if entry.is_directory:
                    info["is_dir"] = True
                if hasattr(entry, "file_size") and entry.file_size is not None:
                    info["size"] = entry.file_size
                if hasattr(entry, "last_modified") and entry.last_modified:
                    info["modified_at"] = str(entry.last_modified)
                results.append(info)
        except Exception as e:
            logger.warning(f"ls_info failed for {physical}: {e}")

        try:
            # List Lakebase tables under the agent's two relevant schemas.
            # Hackathon Wave 3: was UC Delta SHOW TABLES, now Postgres
            # information_schema. See decisions doc 2026-05-13.
            with self._pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT table_schema, table_name
                        FROM information_schema.tables
                        WHERE table_schema IN (%s, 'unhcr')
                          AND table_type = 'BASE TABLE'
                        ORDER BY table_schema, table_name
                        """,
                        (self._lakebase_scratch_schema,),
                    )
                    for tschema, tname in cur.fetchall():
                        # Virtual path uses 'schema/table' so it's stat-able by ls/glob.
                        results.append({"path": f"/tables/{tschema}/{tname}", "is_dir": False})
        except Exception as e:
            logger.warning(f"Failed to list Lakebase tables: {e}")

        # Include /notebooks/ as a virtual directory at root level
        if path == "/":
            results.append({"path": "/notebooks/", "is_dir": True})

        self._log_operation("ls", path, physical_path=physical)
        return results

    def _ls_notebooks(self, path="/notebooks"):
        """List Databricks notebooks in the agent_generated workspace directory."""
        notebook_base = self._get_notebook_base()
        results = []
        try:
            for obj in self._w.workspace.list(notebook_base):
                name = obj.path.split("/")[-1] if obj.path else ""
                results.append({
                    "path": f"/notebooks/{name}",
                    "is_dir": False,
                    "modified_at": str(obj.modified_at) if hasattr(obj, "modified_at") and obj.modified_at else None,
                })
        except Exception as e:
            logger.warning(f"_ls_notebooks failed: {e}")

        self._log_operation("ls_notebooks", path, "workspace", notebook_base)
        return results

    async def als_info(self, path="/"):
        return self.ls_info(path)

    # --- read ---

    def read(self, file_path, offset=0, limit=2000):
        # Route /notebooks/ paths to Workspace export
        if self._is_notebook_path(file_path):
            return self._read_notebook(file_path, offset, limit)

        if file_path.startswith("/tables/"):
            schema, table = self._parse_tables_path(file_path)
            fqn = f'"{schema}"."{table}"'
            try:
                with self._pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(f"SELECT * FROM {fqn} LIMIT %s OFFSET %s", (limit, offset))
                        columns = [d.name for d in cur.description] if cur.description else []
                        data = cur.fetchall()

                lines = []
                if columns:
                    lines.append("\t".join(columns))
                for i, row in enumerate(data):
                    line_num = offset + i + 1
                    row_str = "\t".join(str(v) if v is not None else "NULL" for v in row)
                    lines.append(f"{line_num:6d}\t{row_str}")

                self._log_operation("read", file_path, "lakebase_table", fqn, row_count=len(data))
                return "\n".join(lines) if lines else "Table exists but has no data."
            except Exception as e:
                self._log_operation("read", file_path, "lakebase_table", fqn, status="error", error_message=str(e))
                return f"Error reading table {fqn}: {e}"

        physical = self._resolve_path(file_path)
        try:
            resp = self._w.files.download(file_path=physical)
            raw = resp.contents.read() if hasattr(resp, "contents") else resp.read()
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)

            lines = content.splitlines()
            start_idx = offset
            end_idx = min(start_idx + limit, len(lines))

            if start_idx >= len(lines) and len(lines) > 0:
                return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

            result_lines = []
            for i in range(start_idx, end_idx):
                result_lines.append(f"{i + 1:6d}\t{lines[i][:2000]}")

            self._log_operation("read", file_path, "volume", physical, size_bytes=len(content))
            return "\n".join(result_lines) if result_lines else "File exists but has empty contents."
        except Exception as e:
            self._log_operation("read", file_path, "volume", physical, status="error", error_message=str(e))
            return f"Error: File '{file_path}' not found or not readable: {e}"

    async def aread(self, file_path, offset=0, limit=2000):
        return self.read(file_path, offset, limit)

    def _read_notebook(self, file_path, offset=0, limit=2000):
        """Read a Databricks notebook from Workspace via export."""
        from databricks.sdk.service.workspace import ExportFormat
        import base64

        notebook_path = self._resolve_notebook_path(file_path)
        try:
            export = self._w.workspace.export(notebook_path, format=ExportFormat.SOURCE)
            raw = base64.b64decode(export.content) if export.content else b""
            content = raw.decode("utf-8", errors="replace")

            lines = content.splitlines()
            start_idx = offset
            end_idx = min(start_idx + limit, len(lines))

            result_lines = []
            for i in range(start_idx, end_idx):
                result_lines.append(f"{i + 1:6d}\t{lines[i][:2000]}")

            self._log_operation("read_notebook", file_path, "workspace", notebook_path, size_bytes=len(content))
            return "\n".join(result_lines) if result_lines else "Notebook exists but is empty."
        except Exception as e:
            self._log_operation("read_notebook", file_path, "workspace", notebook_path, status="error", error_message=str(e))
            return f"Error: Notebook '{file_path}' not found: {e}"

    # --- write ---

    def write(self, file_path, content):
        # Route notebook-like writes to Workspace as Databricks notebooks
        if self._looks_like_notebook(file_path, content):
            return self._write_notebook(file_path, content)

        physical = self._resolve_path(file_path)

        parent = str(PurePosixPath(physical).parent)
        try:
            self._w.files.get_directory_metadata(parent)
        except Exception:
            try:
                self._w.files.create_directory(parent)
            except Exception:
                pass

        try:
            content_bytes = content.encode("utf-8")
            self._w.files.upload(
                file_path=physical, contents=io.BytesIO(content_bytes), overwrite=True,
            )
            self._log_operation("write", file_path, "volume", physical, size_bytes=len(content_bytes))
            return WriteResult(path=file_path)
        except Exception as e:
            self._log_operation("write", file_path, "volume", physical, status="error", error_message=str(e))
            return WriteResult(error=f"Failed to write {file_path}: {e}")

    def _write_notebook(self, file_path, content):
        """Write content as a Databricks notebook to Workspace."""
        from databricks.sdk.service.workspace import ImportFormat, Language

        notebook_path = self._resolve_notebook_path(file_path)

        # Convert .ipynb JSON to Databricks notebook source format
        if content.lstrip().startswith("{"):
            try:
                nb = json.loads(content)
                if "cells" in nb:
                    cells = []
                    for cell in nb["cells"]:
                        src = "".join(cell.get("source", []))
                        if cell.get("cell_type") == "markdown":
                            # Convert markdown cells to MAGIC %md
                            md_lines = "\n".join(f"# MAGIC {line}" for line in src.splitlines())
                            cells.append(f"# MAGIC %md\n{md_lines}")
                        else:
                            cells.append(src)
                    content = "# Databricks notebook source\n" + "\n\n# COMMAND ----------\n\n".join(cells)
                    logger.info(f"Converted ipynb ({len(nb['cells'])} cells) to Databricks source format")
            except (json.JSONDecodeError, KeyError):
                pass  # Not valid ipynb JSON, treat as raw code

        # Wrap raw code in Databricks notebook format if not already
        if not content.startswith("# Databricks notebook source"):
            content = (
                "# Databricks notebook source\n"
                "\n# COMMAND ----------\n\n"
                f"{content}\n"
            )

        try:
            content_bytes = content.encode("utf-8")
            self._w.workspace.upload(
                notebook_path,
                io.BytesIO(content_bytes),
                format=ImportFormat.SOURCE,
                language=Language.PYTHON,
                overwrite=True,
            )
            # Get the notebook URL (modern /editor/notebooks/... form with
            # ?o=<workspace_id> so the LLM surfaces a canonical URL rather
            # than rewriting the legacy /#notebook/ form and fabricating
            # the workspace id from its training data).
            try:
                obj = self._w.workspace.get_status(notebook_path)
                host = self._w.config.host.rstrip("/")
                m = re.match(
                    r"^https?://adb-(\d+)\.\d+\.azuredatabricks\.net$", host,
                )
                ws_id = m.group(1) if m else None
                if ws_id:
                    notebook_url = f"{host}/editor/notebooks/{obj.object_id}?o={ws_id}"
                else:
                    notebook_url = f"{host}/editor/notebooks/{obj.object_id}"
            except Exception:
                notebook_url = notebook_path

            self._log_operation(
                "write_notebook", file_path, "workspace", notebook_path,
                size_bytes=len(content_bytes),
                metadata={"notebook_url": notebook_url},
            )
            return WriteResult(path=f"{file_path} → saved as Databricks notebook at {notebook_path} ({notebook_url})")
        except Exception as e:
            self._log_operation(
                "write_notebook", file_path, "workspace", notebook_path,
                status="error", error_message=str(e),
            )
            return WriteResult(error=f"Failed to create notebook {notebook_path}: {e}")

    async def awrite(self, file_path, content):
        return self.write(file_path, content)

    # --- edit ---

    def edit(self, file_path, old_string, new_string, replace_all=False):
        physical = self._resolve_path(file_path)

        try:
            resp = self._w.files.download(file_path=physical)
            raw = resp.contents.read() if hasattr(resp, "contents") else resp.read()
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        except Exception as e:
            return EditResult(error=f"File '{file_path}' not found: {e}")

        if old_string not in content:
            return EditResult(error=f"String not found in '{file_path}'")

        if replace_all:
            count = content.count(old_string)
            new_content = content.replace(old_string, new_string)
        else:
            if content.count(old_string) > 1:
                return EditResult(
                    error=f"Multiple occurrences found in '{file_path}'. Use replace_all=True."
                )
            count = 1
            new_content = content.replace(old_string, new_string, 1)

        try:
            self._w.files.upload(
                file_path=physical, contents=io.BytesIO(new_content.encode("utf-8")), overwrite=True,
            )
            self._log_operation("edit", file_path, "volume", physical, size_bytes=len(new_content))
            return EditResult(path=file_path, occurrences=count)
        except Exception as e:
            return EditResult(error=f"Failed to write edit to {file_path}: {e}")

    async def aedit(self, file_path, old_string, new_string, replace_all=False):
        return self.edit(file_path, old_string, new_string, replace_all)

    # --- grep_raw ---

    def grep_raw(self, pattern, path=None, glob=None):
        search_path = path or "/"
        physical = self._resolve_path(search_path)
        matches = []

        try:
            files_to_search = []
            for entry in self._w.files.list_directory_contents(physical):
                if entry.is_directory:
                    continue
                name = entry.name or ""
                if glob and not fnmatch.fnmatch(name, glob):
                    continue
                files_to_search.append(name)

            for fname in files_to_search[:50]:
                fpath = f"{physical}/{fname}"
                try:
                    resp = self._w.files.download(file_path=fpath)
                    raw = resp.contents.read() if hasattr(resp, "contents") else resp.read()
                    content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                    for i, line in enumerate(content.splitlines(), 1):
                        if pattern in line:
                            vpath = f"{search_path.rstrip('/')}/{fname}"
                            matches.append({"path": vpath, "line": i, "text": line[:500]})
                except Exception:
                    continue
        except Exception as e:
            self._log_operation("grep", search_path, status="error", error_message=str(e))
            return f"Error searching files: {e}"

        self._log_operation("grep", search_path, metadata={"pattern": pattern, "matches": len(matches)})
        return matches

    async def agrep_raw(self, pattern, path=None, glob=None):
        return self.grep_raw(pattern, path, glob)

    # --- glob_info ---

    def glob_info(self, pattern, path="/"):
        physical = self._resolve_path(path)
        results = []

        try:
            for entry in self._w.files.list_directory_contents(physical):
                name = entry.name or ""
                if fnmatch.fnmatch(name, pattern):
                    entry_path = f"{path.rstrip('/')}/{name}"
                    info = {"path": entry_path}
                    if entry.is_directory:
                        info["is_dir"] = True
                    if hasattr(entry, "file_size") and entry.file_size is not None:
                        info["size"] = entry.file_size
                    results.append(info)
        except Exception as e:
            logger.warning(f"glob_info failed: {e}")

        self._log_operation("glob", path, metadata={"pattern": pattern, "matches": len(results)})
        return results

    async def aglob_info(self, pattern, path="/"):
        return self.glob_info(pattern, path)

    # --- upload / download ---

    def upload_files(self, files):
        results = []
        for vpath, content in files:
            physical = self._resolve_path(vpath)
            try:
                parent = str(PurePosixPath(physical).parent)
                try:
                    self._w.files.create_directory(parent)
                except Exception:
                    pass
                self._w.files.upload(file_path=physical, contents=io.BytesIO(content), overwrite=True)
                self._log_operation("upload", vpath, "volume", physical, size_bytes=len(content))
                results.append({"path": vpath, "error": None})
            except Exception as e:
                self._log_operation("upload", vpath, "volume", physical, status="error", error_message=str(e))
                results.append({"path": vpath, "error": str(e)})
        return results

    def download_files(self, paths):
        results = []
        for vpath in paths:
            physical = self._resolve_path(vpath)
            try:
                resp = self._w.files.download(file_path=physical)
                content = resp.contents.read() if hasattr(resp, "contents") else resp.read()
                self._log_operation("download", vpath, "volume", physical, size_bytes=len(content))
                results.append({"path": vpath, "content": content, "error": None})
            except Exception as e:
                self._log_operation("download", vpath, "volume", physical, status="error", error_message=str(e))
                results.append({"path": vpath, "content": None, "error": str(e)})
        return results

    async def aupload_files(self, files):
        return self.upload_files(files)

    async def adownload_files(self, paths):
        return self.download_files(paths)

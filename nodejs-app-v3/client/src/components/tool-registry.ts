/**
 * How a backend tool surfaces in the UI.
 *
 * - `glyph`        — single-char icon used in tool rows / chips
 * - `actionLabel`  — gerund used in the in-conversation tool row ("Reading file")
 * - `noun`         — short category noun used in the activity-panel chips ("File reader")
 * - `category`     — coarse bucket for analytics
 */
export type ToolPresentation = {
  glyph: string;
  actionLabel: string;
  noun: string;
  category: 'data' | 'code' | 'plan' | 'file' | 'web' | 'render' | 'memory' | 'other';
};

// Glyph tokens are kebab-case Lucide icon names. <ToolGlyph> renders the
// corresponding lucide-react component. See tool-row.tsx → ToolGlyph for the
// token → component lookup.
const REGISTRY: Record<string, ToolPresentation> = {
  // Data retrieval. Genie row uses sparkles (replaces the genie-lamp SVG).
  ask_genie_space: { glyph: 'sparkles', actionLabel: 'Querying Genie space', noun: 'Genie space', category: 'data' },
  run_spark_sql: { glyph: 'chart-bar-stacked', actionLabel: 'Running Spark SQL', noun: 'Spark SQL', category: 'data' },
  query_stored_dfs: { glyph: 'chart-bar-stacked', actionLabel: 'Querying stored DataFrames', noun: 'DataFrame queries', category: 'data' },
  describe_dataframe: { glyph: 'file-braces', actionLabel: 'Describing DataFrame', noun: 'DataFrame schema', category: 'data' },

  // Code execution
  run_python_code: { glyph: 'code', actionLabel: 'Running Python', noun: 'Python', category: 'code' },
  run_python_notebook: { glyph: 'code', actionLabel: 'Running notebook', noun: 'Notebook runner', category: 'code' },
  save_python_notebook: { glyph: 'file-braces', actionLabel: 'Saving notebook', noun: 'Notebook writer', category: 'file' },

  // Render
  render_chart: { glyph: 'chart-bar-stacked', actionLabel: 'Rendering chart', noun: 'Chart renderer', category: 'render' },
  compose_infographic: { glyph: 'chart-bar-stacked', actionLabel: 'Composing infographic', noun: 'Infographic composer', category: 'render' },
  compose_document: { glyph: 'file-braces', actionLabel: 'Composing document', noun: 'Document composer', category: 'file' },

  // Planning / reasoning
  think_tool: { glyph: 'brain', actionLabel: 'Thinking', noun: 'Reasoning', category: 'plan' },
  write_todos: { glyph: 'notebook-pen', actionLabel: 'Updating plan', noun: 'Plan', category: 'plan' },
  read_todos: { glyph: 'notebook-pen', actionLabel: 'Reading plan', noun: 'Plan', category: 'plan' },
  taskcreate: { glyph: 'notebook-pen', actionLabel: 'Creating task', noun: 'Plan', category: 'plan' },
  taskupdate: { glyph: 'notebook-pen', actionLabel: 'Updating task', noun: 'Plan', category: 'plan' },

  // File / FS
  read_file: { glyph: 'file-braces', actionLabel: 'Reading file', noun: 'File reader', category: 'file' },
  write_file: { glyph: 'file-braces', actionLabel: 'Writing file', noun: 'File writer', category: 'file' },
  edit_file: { glyph: 'file-braces', actionLabel: 'Editing file', noun: 'File editor', category: 'file' },
  ls: { glyph: 'file-braces', actionLabel: 'Listing files', noun: 'File system', category: 'file' },
  glob: { glyph: 'file-braces', actionLabel: 'Globbing files', noun: 'File system', category: 'file' },
  grep: { glyph: 'file-braces', actionLabel: 'Grepping files', noun: 'File search', category: 'file' },
  compact_ref: { glyph: 'file-braces', actionLabel: 'Compacting reference', noun: 'Reference compactor', category: 'file' },

  // Sub-agent
  task: { glyph: 'check-big', actionLabel: 'Sub-agent', noun: 'Sub-agents', category: 'other' },

  // Memory / preferences
  save_user_preference: { glyph: 'user-pen', actionLabel: 'Saving preference', noun: 'User memory', category: 'memory' },
  recall_memory: { glyph: 'user-pen', actionLabel: 'Recalling memory', noun: 'User memory', category: 'memory' },
  manage_memory: { glyph: 'user-pen', actionLabel: 'Updating memory', noun: 'User memory', category: 'memory' },

  // Web — Lucide Search.
  web_search: { glyph: 'search', actionLabel: 'Searching web', noun: 'Web search', category: 'web' },
  fetch: { glyph: 'search', actionLabel: 'Fetching URL', noun: 'Web fetch', category: 'web' },
};

/**
 * Look up a tool by name. Unknown tools fall through to a tidy default.
 */
export function presentTool(toolName: string): ToolPresentation {
  if (!toolName) return { glyph: 'check-big', actionLabel: 'Tool', noun: 'Tool', category: 'other' };

  const normal = toolName.toLowerCase().replace(/^functions\./, '');
  if (REGISTRY[normal]) return REGISTRY[normal];

  // Title-case for unknown tools
  const titled = toolName
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b(\w)/g, (m) => m.toUpperCase());

  const lower = normal;
  let glyph = 'check-big';
  let category: ToolPresentation['category'] = 'other';
  if (lower.includes('search') || lower.includes('fetch') || lower.includes('web')) {
    glyph = 'search';
    category = 'web';
  } else if (lower.includes('sql') || lower.includes('query') || lower.includes('genie') || lower.includes('data')) {
    glyph = 'chart-bar-stacked';
    category = 'data';
  } else if (lower.includes('chart') || lower.includes('render') || lower.includes('plot')) {
    glyph = 'chart-bar-stacked';
    category = 'render';
  } else if (lower.includes('python') || lower.includes('code') || lower.includes('exec')) {
    glyph = 'code';
    category = 'code';
  } else if (lower.includes('file') || lower.includes('write') || lower.includes('read') || lower.includes('save')) {
    glyph = 'file-braces';
    category = 'file';
  } else if (lower.includes('todo') || lower.includes('plan') || lower.includes('task')) {
    glyph = 'notebook-pen';
    category = 'plan';
  } else if (lower.includes('memory') || lower.includes('pref') || lower.includes('recall')) {
    glyph = 'user-pen';
    category = 'memory';
  }

  return { glyph, actionLabel: titled, noun: titled, category };
}

/**
 * Build the in-row action label with a contextual snippet pulled from the
 * tool's input, so a generic "Reading file" becomes "Reading /skills/SKILL.md".
 *
 * Returns just the action label if nothing useful can be extracted.
 */
export function presentToolRow(
  toolName: string,
  input: unknown,
): { glyph: string; label: string; category: ToolPresentation['category'] } {
  const p = presentTool(toolName);
  const ctx = extractContext(toolName, input);
  return {
    glyph: p.glyph,
    label: ctx ? `${p.actionLabel} · ${ctx}` : p.actionLabel,
    category: p.category,
  };
}

// Hackathon Genie spaces — keep in sync with hackathon-skills/domains/SKILL.md.
// Add new spaces here when wiring additional domains.
const GENIE_SPACE_NAMES: Record<string, string> = {
  '01f168ec4bf01d27a00ac8069c1b06b8': 'India Healthcare Access',
};

const SHORTEN_PATH_PREFIXES = ['/Workspace/', '/Volumes/'];

function shortenPath(p: string, max = 36): string {
  if (!p) return p;
  let s = p;
  for (const pre of SHORTEN_PATH_PREFIXES) {
    if (s.startsWith(pre)) s = `…${s.slice(pre.length)}`;
    break;
  }
  if (s.length > max) {
    // Keep the tail (filename + parent dir)
    const parts = s.split('/');
    if (parts.length >= 3) {
      s = `…/${parts.slice(-2).join('/')}`;
    }
  }
  if (s.length > max) s = `${s.slice(0, max - 1)}…`;
  return s;
}

function shortenString(s: string, max = 28): string {
  if (!s) return s;
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}…`;
}

function extractContext(toolName: string, input: unknown): string | undefined {
  if (input == null || typeof input !== 'object') return undefined;
  const o = input as Record<string, unknown>;
  const lower = toolName.toLowerCase().replace(/^functions\./, '');

  // File operations
  if (typeof o.file_path === 'string') return shortenPath(o.file_path);
  if (typeof o.path === 'string') return shortenPath(o.path);
  if (typeof o.notebook_path === 'string') return shortenPath(o.notebook_path);
  if (typeof o.url === 'string') return shortenString(o.url, 36);

  // Genie / SQL — show human Genie Space name, not the cryptic UUID suffix.
  if (lower.includes('genie')) {
    const sid = o.space_id ?? o.spaceId ?? o.id;
    if (typeof sid === 'string' && sid.length >= 6) {
      const name = GENIE_SPACE_NAMES[sid];
      if (name) return name;
      // Fall back to question excerpt if we don't recognize the space.
      if (typeof o.question === 'string') return shortenString(o.question, 36);
      return `space …${sid.slice(-6)}`;
    }
    if (typeof o.question === 'string') return shortenString(o.question, 36);
  }
  if (typeof o.query === 'string') return shortenString(o.query.replace(/\s+/g, ' '), 36);
  if (typeof o.sql === 'string') return shortenString(o.sql.replace(/\s+/g, ' '), 36);

  // Search
  if (typeof o.q === 'string') return shortenString(o.q, 36);
  if (typeof o.search === 'string') return shortenString(o.search, 36);

  // Glob / grep
  if (typeof o.pattern === 'string') return shortenString(o.pattern, 28);

  // Python
  if (typeof o.code === 'string') return shortenString(o.code.split('\n')[0], 36);

  // Render chart
  if (typeof o.chart_type === 'string') return o.chart_type;
  if (typeof o.title === 'string') return shortenString(o.title, 32);

  // Subagent / task
  if (typeof o.subagent_type === 'string') return o.subagent_type;
  if (typeof o.description === 'string') return shortenString(o.description, 36);

  // Plan / todos
  if (Array.isArray(o.todos)) return `${o.todos.length} item${o.todos.length === 1 ? '' : 's'}`;

  // Memory
  if (typeof o.content === 'string') return shortenString(o.content, 36);

  return undefined;
}

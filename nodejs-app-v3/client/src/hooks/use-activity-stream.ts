import { useMemo } from 'react';
import type { ChatMessage } from '@chat-template/core';
import { presentTool, type ToolPresentation } from '@/components/tool-registry';

export type ProgressStep = {
  id: string;
  label: string;
  state: 'pending' | 'active' | 'done';
};

export type ArtifactRow = {
  id: string;
  name: string;
  glyph: string;
  href?: string;
  ext?: string;
};

export type SkillChip = {
  name: string;
  glyph: string;
  category: ToolPresentation['category'];
};

/**
 * Extracts a coarse-grained "current task plan" + working folder + skill set
 * out of the existing assistant message stream. Read-only — no SSE shape changes.
 *
 * Heuristics:
 * - Progress steps come from `write_todos` / `read_todos` tool invocations: the
 *   most recent input that contains a list of todos wins. Each todo's
 *   `status` ("pending"/"in_progress"/"completed") maps to badge state.
 *   If no todos found, we synthesize a single "Working" step while the
 *   assistant is streaming, otherwise empty.
 * - Working folder rows come from `save_python_notebook`, `render_chart`,
 *   `compose_infographic`, and any tool with an `output.url` / `output.path`.
 * - Skill chips come from the unique set of tool names invoked in the
 *   conversation, mapped through the tool registry.
 */
export function useActivityStream(
  messages: ChatMessage[],
  status: 'submitted' | 'streaming' | 'ready' | 'error',
) {
  return useMemo(() => {
    const progress: ProgressStep[] = [];
    const folder: ArtifactRow[] = [];
    const skills: SkillChip[] = [];
    const seenSkills = new Set<string>();
    const seenFolderIds = new Set<string>();

    let latestTodos: ProgressStep[] | null = null;

    for (const msg of messages) {
      if (msg.role !== 'assistant') continue;
      for (const part of msg.parts ?? []) {
        if (part.type !== 'dynamic-tool') continue;
        const toolPart = part as {
          type: 'dynamic-tool';
          toolName: string;
          state: string;
          input?: unknown;
          output?: unknown;
          toolCallId?: string;
        };

        // Track skill chip — use the noun form ("File reader") not the action ("Reading file")
        const presentation = presentTool(toolPart.toolName);
        if (!seenSkills.has(presentation.noun)) {
          seenSkills.add(presentation.noun);
          skills.push({
            name: presentation.noun,
            glyph: presentation.glyph,
            category: presentation.category,
          });
        }

        // Plan extraction. AI SDK may forward `input` as either a parsed
        // object or a JSON-encoded string (the same way Python tools return
        // json.dumps for `output`). Parse defensively before shape-checking.
        const lower = toolPart.toolName.toLowerCase();
        if (lower.includes('todo') || lower === 'taskcreate' || lower === 'taskupdate') {
          const inputObj = parseMaybeJsonObject(toolPart.input);
          const list = (inputObj?.todos ?? inputObj?.tasks ?? inputObj) as unknown;
          const extracted = extractTodos(list);
          if (extracted?.length) {
            latestTodos = extracted;
          }
        }

        // Working folder — output may be a JSON STRING (Python tools call
        // json.dumps), so parse before shape-checking. Otherwise every
        // Python-side artifact is silently lost.
        let out: Record<string, unknown> | undefined;
        const rawOut = toolPart.output;
        if (typeof rawOut === 'string') {
          const trimmed = rawOut.trim();
          if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
            try {
              const p = JSON.parse(trimmed);
              if (p && typeof p === 'object') out = p as Record<string, unknown>;
            } catch {
              /* not JSON — leave undefined */
            }
          }
        } else if (rawOut && typeof rawOut === 'object') {
          out = rawOut as Record<string, unknown>;
        }
        const fileName =
          (out?.path as string | undefined) ||
          (out?.url as string | undefined) ||
          (out?.notebook_path as string | undefined) ||
          (out?.file_path as string | undefined) ||
          (out?.html_path as string | undefined);
        const chartId = out?.chart_id as string | undefined;
        const infographicId = out?.infographic_id as string | undefined;
        const documentId = out?.document_id as string | undefined;
        const docFormat = (out?.format as string | undefined)?.toLowerCase();
        if (documentId) {
          const id = `document:${documentId}`;
          if (!seenFolderIds.has(id)) {
            seenFolderIds.add(id);
            // Decks → /api/decks/<id>.pptx; other docs → /api/documents/<id>.
            const isDeck = documentId.startsWith('deck_');
            folder.push({
              id,
              name:
                (out?.title as string | undefined) ??
                `${documentId}${docFormat ? `.${docFormat}` : ''}`,
              glyph: 'file-braces',
              href: isDeck
                ? `/api/decks/${encodeURIComponent(documentId)}.pptx`
                : `/api/documents/${encodeURIComponent(documentId)}`,
              ext: isDeck ? 'PPTX' : docFormat ? docFormat.toUpperCase() : undefined,
            });
          }
        } else if (infographicId) {
          // Prefer the infographic_id form — title is the editorial label
          // the user sees, the href is the proxied server route the iframe
          // hits ("server-fetches-from-Volumes" per /api/infographics).
          const id = `infographic:${infographicId}`;
          if (!seenFolderIds.has(id)) {
            seenFolderIds.add(id);
            folder.push({
              id,
              name: (out?.title as string | undefined) || `${infographicId}.html`,
              glyph: 'chart-bar-stacked',
              href: `/api/infographics/${encodeURIComponent(infographicId)}`,
              ext: 'HTML',
            });
          }
        } else if (fileName) {
          const id = String(fileName);
          if (!seenFolderIds.has(id)) {
            seenFolderIds.add(id);
            folder.push({
              id,
              name: prettyName(id),
              glyph: pickFolderGlyph(id),
              href: id.startsWith('http') ? id : undefined,
              ext: extensionOf(id),
            });
          }
        } else if (chartId) {
          const id = `chart:${chartId}`;
          if (!seenFolderIds.has(id)) {
            seenFolderIds.add(id);
            folder.push({
              id,
              name: `chart-${chartId.slice(0, 6)}.html`,
              glyph: 'chart-bar-stacked',
              href: `/api/charts/${encodeURIComponent(chartId)}`,
              ext: 'HTML',
            });
          }
        }
      }
    }

    // Sub-agent created artifacts (e.g. python-analyst's save_python_notebook)
    // never surface as orchestrator-level dynamic-tool outputs — they bubble up
    // as a "task" tool result whose `update.messages[].content` carries the
    // URL as plain text. Scan every assistant text part for notebook / chart /
    // infographic / volume URLs the tool-output walk missed.
    for (const msg of messages) {
      if (msg.role !== 'assistant') continue;
      for (const part of msg.parts ?? []) {
        if (part.type !== 'text') continue;
        const text = (part as { text?: string }).text ?? '';
        if (!text) continue;
        for (const found of scanTextForArtifacts(text)) {
          if (seenFolderIds.has(found.id)) continue;
          seenFolderIds.add(found.id);
          folder.push(found);
        }
      }
    }

    if (latestTodos?.length) {
      progress.push(...latestTodos);
    } else if (status === 'streaming' || status === 'submitted') {
      progress.push({ id: 'live', label: 'Working on your message', state: 'active' });
    }

    return { progress, folder, skills };
  }, [messages, status]);
}

function parseMaybeJsonObject(raw: unknown): Record<string, unknown> | undefined {
  if (raw == null) return undefined;
  if (typeof raw === 'object') return raw as Record<string, unknown>;
  if (typeof raw !== 'string') return undefined;
  const trimmed = raw.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return undefined;
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object') return parsed as Record<string, unknown>;
  } catch {
    /* not JSON — leave undefined */
  }
  return undefined;
}

function extractTodos(raw: unknown): ProgressStep[] | null {
  if (!Array.isArray(raw)) return null;
  const out: ProgressStep[] = [];
  for (let i = 0; i < raw.length; i++) {
    const t = raw[i] as Record<string, unknown> | string;
    if (typeof t === 'string') {
      out.push({ id: `todo-${i}`, label: t, state: 'pending' });
      continue;
    }
    if (typeof t !== 'object' || t == null) continue;
    // DeepAgents emits `content` (verified against MLflow span input). Older
    // / sibling implementations use `task`, `subject`, etc. — keep the
    // fallback chain wide so we don't silently drop plans across versions.
    const label =
      (t.content as string | undefined) ??
      (t.task as string | undefined) ??
      (t.subject as string | undefined) ??
      (t.label as string | undefined) ??
      (t.text as string | undefined) ??
      (t.title as string | undefined) ??
      (t.description as string | undefined);
    if (!label) continue;
    const status = String(t.status ?? t.state ?? 'pending').toLowerCase();
    let mapped: ProgressStep['state'] = 'pending';
    if (['in_progress', 'in-progress', 'active', 'running', 'doing'].includes(status)) mapped = 'active';
    else if (['completed', 'done', 'finished', 'closed'].includes(status)) mapped = 'done';
    out.push({ id: String(t.id ?? `todo-${i}`), label, state: mapped });
  }
  return out;
}

/**
 * Pull artifact rows out of a markdown / plain-text assistant message body.
 * Covers the case where a sub-agent (python-analyst, data-viz) creates a
 * notebook or chart — the URL lands in the assistant's prose, never as an
 * orchestrator-level tool output. Recognised:
 *   - https://…/editor/notebooks/<id>       → Databricks notebook
 *   - https://…/files/Workspace/…/Volumes/… → UC Volumes file
 *   - /api/charts/<id>                       → server-proxied chart HTML
 *   - /api/infographics/<id>                 → server-proxied infographic
 */
function scanTextForArtifacts(text: string): ArtifactRow[] {
  const found: ArtifactRow[] = [];
  const seen = new Set<string>();

  const push = (row: ArtifactRow) => {
    if (seen.has(row.id)) return;
    seen.add(row.id);
    found.push(row);
  };

  // Markdown title for a given URL: [title](url) — prefer that over a path-derived basename.
  const titleFor = (url: string): string | undefined => {
    const re = new RegExp(`\\[([^\\]]+)\\]\\(${escapeRegex(url)}[^)]*\\)`);
    const m = re.exec(text);
    return m ? m[1].trim() : undefined;
  };

  // Databricks editor/notebooks/<id>
  const notebookRe = /https?:\/\/[^\s)]+\/editor\/notebooks\/(\d+)[^\s)]*/g;
  for (const m of text.matchAll(notebookRe)) {
    const url = m[0];
    const id = `notebook:${m[1]}`;
    const title = titleFor(url) ?? `notebook-${m[1].slice(-6)}.ipynb`;
    push({ id, name: title, glyph: 'code', href: url, ext: 'ipynb' });
  }

  // Local proxy paths the server already serves
  const proxyRe = /\/api\/(charts|infographics|documents)\/([A-Za-z0-9_\-]+)/g;
  for (const m of text.matchAll(proxyRe)) {
    const kind = m[1];
    const slug = m[2];
    const singular =
      kind === 'infographics' ? 'infographic'
      : kind === 'documents' ? 'document'
      : 'chart';
    const id = `${singular}:${slug}`;
    const url = `/api/${kind}/${slug}`;
    const title = titleFor(url) ?? `${singular}-${slug.slice(0, 8)}`;
    const glyph = singular === 'document' ? 'file-braces' : 'chart-bar-stacked';
    const ext = singular === 'document' ? undefined : 'HTML';
    push({ id, name: title, glyph, href: url, ext });
  }

  return found;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function prettyName(p: string): string {
  if (p.startsWith('http')) {
    try {
      const url = new URL(p);
      const last = url.pathname.split('/').filter(Boolean).pop();
      return last || url.host;
    } catch {
      // fallthrough
    }
  }
  const last = p.split('/').filter(Boolean).pop() || p;
  return last;
}

function extensionOf(p: string): string | undefined {
  const m = /\.(\w+)(?:[?#]|$)/.exec(p);
  return m ? m[1].toUpperCase() : undefined;
}

function pickFolderGlyph(p: string): string {
  const ext = extensionOf(p)?.toLowerCase();
  if (!ext) return 'file-braces';
  if (ext === 'ipynb' || ext === 'py' || ext === 'sql') return 'code';
  if (ext === 'html' || ext === 'svg' || ext === 'png' || ext === 'jpg') return 'chart-bar-stacked';
  return 'file-braces';
}

import { useEffect, useMemo, useState } from 'react';
import type { ChatMessage } from '@chat-template/core';

export type Artifact = {
  id: string;
  title: string;
  ext?: string;
  /** A URL the iframe (or download link) can load directly. */
  href?: string;
  /** Inline HTML (rendered via srcdoc) when no URL is available. */
  srcdoc?: string;
  /** Source message id (so the chip can sit under the right bubble). */
  messageId: string;
  toolCallId: string;
  /**
   * Binary office docs (pptx/docx/xlsx/csv/pdf) can't be iframed — the dock
   * renders a download card instead. When set, the dock uses this hint to
   * pick the right surface; `kind === 'document'` means "show the download
   * card, never try to iframe".
   */
  kind?: 'html' | 'document';
  /** Optional file size in bytes — surfaced on the download card. */
  sizeBytes?: number;
  /** Optional format slug ("pptx", "pdf", …) for the download card icon. */
  format?: string;
};

/**
 * Walks the assistant message stream and pulls every renderable artifact
 * (charts, infographics, generated HTML/SVG) into a single ordered list.
 * Order is the order the parts appeared in the conversation.
 *
 * Detection is best-effort against shapes the orchestrator might emit:
 *   - { chart_id, html_url? | source_url? | url? }
 *   - { infographic_id, source_url }
 *   - { html: "<!doctype html>..." }
 *   - { svg: "<svg ...>" }
 *   - { url: ".../*.html" }
 */
export function useArtifacts(messages: ChatMessage[]) {
  return useMemo(() => {
    const artifacts: Artifact[] = [];
    for (const msg of messages) {
      if (msg.role !== 'assistant') continue;
      for (const part of msg.parts ?? []) {
        if (part.type !== 'dynamic-tool') continue;
        const toolPart = part as {
          type: 'dynamic-tool';
          toolName: string;
          toolCallId: string;
          state: string;
          output?: unknown;
        };
        if (toolPart.state !== 'output-available') continue;
        const out = toolPart.output;
        const artifact = artifactFromToolOutput(out, msg.id, toolPart.toolCallId);
        if (artifact) artifacts.push(artifact);
      }
    }
    return artifacts;
  }, [messages]);
}

function artifactFromToolOutput(
  out: unknown,
  messageId: string,
  toolCallId: string,
): Artifact | null {
  if (out == null) return null;
  // Python tools return `json.dumps(...)` so the SDK forwards a string here.
  // Parse it before shape-checking — otherwise `typeof out !== 'object'` bails
  // and we silently lose every Python-side artifact.
  let parsed: unknown = out;
  if (typeof out === 'string') {
    // find_skill returns a markdown PLAN (not JSON) ending in a traversal-graph
    // link served by /api/skill_graph — surface it as an iframable artifact.
    const graphMatch =
      /(?:https?:\/\/[^\s)]+)?(\/api\/skill_graph\/(?:skillgraph_)?[a-f0-9]{8,16}\.html)/.exec(
        out,
      );
    if (graphMatch) {
      return {
        id: toolCallId,
        messageId,
        toolCallId,
        title: 'Knowledge-graph traversal',
        ext: 'HTML',
        href: graphMatch[1],
      };
    }
    const trimmed = out.trim();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return null;
    }
  }
  if (parsed == null || typeof parsed !== 'object') return null;
  const o = parsed as Record<string, unknown>;

  const chartId = pickStr(o, ['chart_id', 'chartId']);
  const infographicId = pickStr(o, ['infographic_id', 'infographicId']);
  const documentId = pickStr(o, ['document_id', 'documentId']);
  const url = pickStr(o, ['source_url', 'sourceUrl', 'html_url', 'htmlUrl', 'url']);
  const html = pickStr(o, ['html']);
  const svg = pickStr(o, ['svg']);
  const titleHint = pickStr(o, ['title', 'name', 'caption']);
  const formatHint = pickStr(o, ['format', 'ext', 'extension']);
  const sizeBytesRaw = o.size_bytes ?? o.sizeBytes ?? o.file_size_bytes;
  const sizeBytes =
    typeof sizeBytesRaw === 'number'
      ? sizeBytesRaw
      : // compose_deck returns size_bytes as { pptx, html } — surface the pptx size.
        typeof (sizeBytesRaw as { pptx?: unknown } | undefined)?.pptx === 'number'
        ? (sizeBytesRaw as { pptx: number }).pptx
        : undefined;

  if (documentId) {
    // Decks (compose_deck) are served from /api/decks/<id>.pptx — NOT
    // /api/documents, whose id pattern is `document_<format>_<hex>` and 400s on
    // a `deck_<hex>` id (that 400 JSON was what got downloaded as the "file").
    const isDeck = documentId.startsWith('deck_');
    const pptxUrl = pickStr(o, ['pptx_url', 'pptxUrl']);
    const href = isDeck
      ? (pptxUrl ?? `/api/decks/${encodeURIComponent(documentId)}.pptx`)
      : (url ?? `/api/documents/${encodeURIComponent(documentId)}`);
    // Binary office doc — the dock renders a download card, never an iframe.
    return {
      id: documentId,
      messageId,
      toolCallId,
      title: titleHint ?? `Document ${documentId.slice(0, 8)}`,
      ext: (isDeck ? 'PPTX' : (formatHint ?? '').toUpperCase()) || undefined,
      href,
      kind: 'document',
      sizeBytes,
      format: isDeck ? 'pptx' : formatHint,
    };
  }

  if (chartId && url) {
    return {
      id: chartId,
      messageId,
      toolCallId,
      title: titleHint ?? `Chart ${chartId.slice(0, 8)}`,
      ext: extOfUrl(url) ?? 'HTML',
      href: url,
    };
  }
  if (chartId) {
    // Fall back to the local proxy path; the host app may serve it later.
    return {
      id: chartId,
      messageId,
      toolCallId,
      title: titleHint ?? `Chart ${chartId.slice(0, 8)}`,
      ext: 'HTML',
      href: `/api/charts/${encodeURIComponent(chartId)}`,
    };
  }
  if (infographicId) {
    return {
      id: infographicId,
      messageId,
      toolCallId,
      title: titleHint ?? `Infographic ${infographicId.slice(0, 8)}`,
      ext: 'HTML',
      href: url ?? `/api/infographics/${encodeURIComponent(infographicId)}`,
    };
  }
  if (html) {
    return {
      id: toolCallId,
      messageId,
      toolCallId,
      title: titleHint ?? 'Generated HTML',
      ext: 'HTML',
      srcdoc: html,
    };
  }
  if (svg) {
    return {
      id: toolCallId,
      messageId,
      toolCallId,
      title: titleHint ?? 'Generated SVG',
      ext: 'SVG',
      srcdoc: `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:#0f0f0f;color:#f5f1eb;display:flex;align-items:center;justify-content:center;height:100%;}</style>${svg}`,
    };
  }
  if (url && /\.(html?|svg)(?:[?#]|$)/i.test(url)) {
    return {
      id: toolCallId,
      messageId,
      toolCallId,
      title: titleHint ?? prettyTitle(url),
      ext: extOfUrl(url) ?? 'HTML',
      href: url,
    };
  }
  return null;
}

function pickStr(o: Record<string, unknown>, keys: string[]): string | undefined {
  for (const k of keys) {
    const v = o[k];
    if (typeof v === 'string' && v.trim()) return v;
  }
  return undefined;
}

function extOfUrl(u: string): string | undefined {
  const m = /\.(\w+)(?:[?#]|$)/.exec(u);
  return m ? m[1].toUpperCase() : undefined;
}

function prettyTitle(u: string): string {
  try {
    const url = new URL(u, 'http://x.local');
    const last = url.pathname.split('/').filter(Boolean).pop();
    return last || u;
  } catch {
    return u;
  }
}

/**
 * State machine for the artifact dock: tracks whether it's open, the active
 * artifact, and auto-opens when a NEW artifact arrives mid-stream.
 */
export function useArtifactDock(artifacts: Artifact[]) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [autoOpened, setAutoOpened] = useState<Set<string>>(() => new Set());

  // Auto-open the first time a new artifact appears
  useEffect(() => {
    if (!artifacts.length) return;
    const last = artifacts[artifacts.length - 1];
    if (!autoOpened.has(last.id)) {
      setAutoOpened((prev) => {
        const next = new Set(prev);
        next.add(last.id);
        return next;
      });
      setOpenId(last.id);
    }
  }, [artifacts, autoOpened]);

  const active = artifacts.find((a) => a.id === openId) ?? null;
  const isOpen = active != null;

  const open = (id: string) => {
    if (typeof window !== 'undefined') {
      const exists = artifacts.some((a) => a.id === id);
      console.warn(
        '[artifact-dock] open()',
        id,
        'found-in-artifacts=',
        exists,
        'current-openId=',
        openId,
      );
    }
    setOpenId(id);
  };

  return {
    isOpen,
    active,
    open,
    close: () => setOpenId(null),
  };
}

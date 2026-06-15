import { useState, useMemo, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { presentTool, presentToolRow } from './tool-registry';
import type { ToolUIPart } from 'ai';
import {
  Brain,
  ChartBarStacked,
  CircleCheckBig,
  Code,
  FileJson,
  NotebookPen,
  Search,
  UserRoundPen,
  type LucideIcon,
} from 'lucide-react';
import { LottieSparkle } from './lottie-sparkle';

type ToolPart = Extract<
  NonNullable<ReturnType<typeof asAny>>,
  { type: 'dynamic-tool' }
>;

function asAny() {
  return null as unknown as { type: 'dynamic-tool' } & {
    toolName: string;
    state: ToolUIPart['state'];
    input?: unknown;
    output?: unknown;
    errorText?: string;
  };
}

export type RowToolPart = {
  toolName: string;
  state: ToolUIPart['state'];
  input?: unknown;
  output?: unknown;
  errorText?: string;
  toolCallId: string;
};

const TERMINAL_STATES: ToolUIPart['state'][] = [
  'output-available',
  'output-error',
  'output-denied',
];

/**
 * Render the glyph slot for a tool row. Glyph values are kebab-case Lucide
 * icon names emitted by tool-registry.ts. Sized at 14px, stroke 1.5 to match
 * Inferred Design v2 weight. `file-braces` resolves to FileJson because Lucide
 * 0.446 hasn't released file-braces yet (visually identical { } file glyph).
 */
const GLYPH_ICONS: Record<string, LucideIcon> = {
  'chart-bar-stacked': ChartBarStacked,
  'file-braces': FileJson,
  code: Code,
  brain: Brain,
  'notebook-pen': NotebookPen,
  'check-big': CircleCheckBig,
  'user-pen': UserRoundPen,
  search: Search,
};

export function ToolGlyph({ glyph }: { glyph: string }) {
  // 'sparkles' (the Genie rows) now renders the animated Lottie orb instead
  // of the static Lucide trio.
  if (glyph === 'sparkles') {
    return <LottieSparkle size={14} />;
  }
  const Icon = GLYPH_ICONS[glyph];
  if (Icon) {
    return <Icon size={14} strokeWidth={1.5} aria-hidden />;
  }
  return <>{glyph}</>;
}

function summarizeMeta(part: RowToolPart): string | undefined {
  // Try to derive a short trailing meta string ("3 fields", "10 results", "~7,697 characters", etc.)
  const out = part.output;
  if (!out) return undefined;
  if (typeof out === 'string') {
    const len = out.length;
    if (len > 80) return `~${len.toLocaleString()} chars`;
    return undefined;
  }
  if (Array.isArray(out))
    return `${out.length} item${out.length === 1 ? '' : 's'}`;
  if (typeof out === 'object') {
    const o = out as Record<string, unknown>;
    if (Array.isArray(o.results)) return `${o.results.length} results`;
    if (Array.isArray(o.rows)) return `${o.rows.length} rows`;
    if (typeof o.row_count === 'number')
      return `${o.row_count.toLocaleString()} rows`;
    if (typeof o.chart_id === 'string')
      return `chart ${(o.chart_id as string).slice(0, 6)}…`;
    const keys = Object.keys(o);
    if (keys.length <= 4)
      return `${keys.length} field${keys.length === 1 ? '' : 's'}`;
  }
  return undefined;
}

export function ToolRow({
  part,
  defaultOpen = false,
  detail,
}: {
  part: RowToolPart;
  defaultOpen?: boolean;
  detail?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const presentation = useMemo(
    () => presentToolRow(part.toolName, part.input),
    [part.toolName, part.input],
  );
  const meta = useMemo(() => summarizeMeta(part), [part]);
  const isStreaming =
    part.state === 'input-streaming' || part.state === 'input-available';
  const isError =
    part.state === 'output-error' || part.state === 'output-denied';

  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-open={open ? 'true' : 'false'}
        className={cn(
          'group flex cursor-pointer items-center gap-2.5 rounded-[6px] py-1.5 text-[14px] transition-colors duration-[120ms]',
          'text-fg-2 hover:text-fg-1',
          isError && 'text-[var(--danger)]',
        )}
        aria-expanded={open}
      >
        <span
          className={cn(
            'inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center text-[14px] leading-none',
            'text-fg-3 group-hover:text-fg-1',
            isError && 'text-[var(--danger)]',
          )}
          aria-hidden
        >
          {isStreaming ? (
            <LottieSparkle variant="thinking" size={14} />
          ) : (
            <ToolGlyph glyph={presentation.glyph} />
          )}
        </span>
        <span className="truncate font-normal text-[14px]">
          {presentation.label}
        </span>
        {meta && (
          <span className="ml-auto max-w-[14ch] truncate text-[12.5px] text-fg-3">
            {meta}
          </span>
        )}
        <span
          className={cn(
            'ml-1 shrink-0 text-[12.5px] text-fg-3 transition-transform duration-[120ms]',
            open && 'rotate-90',
            !meta && 'ml-auto',
          )}
          aria-hidden
        >
          ›
        </span>
      </button>

      {open && (detail || hasInlineDetail(part)) && (
        <div className="mt-1 mb-2 ml-[28px] animate-[slide-up-in_240ms_var(--ease-spring)]">
          {detail ?? <DefaultToolDetail part={part} />}
        </div>
      )}
    </div>
  );
}

function hasInlineDetail(part: RowToolPart): boolean {
  if (TERMINAL_STATES.includes(part.state)) return true;
  if (part.input && Object.keys(part.input as object).length > 0) return true;
  return false;
}

function DefaultToolDetail({ part }: { part: RowToolPart }) {
  const isError =
    part.state === 'output-error' || part.state === 'output-denied';
  const body = part.errorText ?? part.output;

  return (
    <div className="flex flex-col gap-2">
      {part.input != null && Object.keys(part.input as object).length > 0 && (
        <details className="text-[12.5px] text-fg-3" open>
          <summary className="cursor-pointer select-none text-fg-3 hover:text-fg-2">
            Parameters
          </summary>
          <pre className="mt-1.5 overflow-x-auto rounded-[6px] border border-border-1 bg-bg-elev-1 px-3 py-2 font-mono text-[12.5px] text-fg-2 leading-snug">
            {JSON.stringify(part.input, null, 2)}
          </pre>
        </details>
      )}
      {body != null && (
        <div
          className={cn(
            'inline-block max-w-full whitespace-pre-wrap break-words rounded-[6px] px-2.5 py-1 font-mono text-[12.5px]',
            isError
              ? 'border border-[var(--border-danger)] bg-[color-mix(in_oklab,var(--danger)_12%,transparent)] text-[var(--danger)]'
              : 'bg-bg-elev-2 text-fg-2',
          )}
        >
          {typeof body === 'string'
            ? body.length > 1200
              ? `${body.slice(0, 1200)}…`
              : body
            : JSON.stringify(body, null, 2)}
        </div>
      )}
    </div>
  );
}

/**
 * Recency-windowed list of tool rows. Only the latest `windowSize` rows render
 * inline; everything older collapses into a "Used N tools, …" summary above.
 */
export function ToolRowWindow({
  parts,
  windowSize = 3,
}: {
  parts: RowToolPart[];
  windowSize?: number;
}) {
  if (!parts.length) return null;

  const overflow = Math.max(0, parts.length - windowSize);
  const visible = parts.slice(-windowSize);

  // Collect unique tool nouns for the summary text
  const usedLabels = useMemo(() => {
    const seen = new Set<string>();
    parts.slice(0, parts.length - visible.length).forEach((p) => {
      seen.add(presentTool(p.toolName).noun.toLowerCase());
    });
    return Array.from(seen);
  }, [parts, visible.length]);

  return (
    <div className="flex flex-col">
      {overflow > 0 && (
        <button
          type="button"
          className="flex cursor-default items-center gap-2 py-1.5 text-left text-[14px] text-fg-3 transition-colors duration-[120ms] hover:text-fg-1"
          aria-label={`${overflow} earlier tool calls hidden`}
        >
          <span aria-hidden className="text-fg-3">
            ›
          </span>
          Used {parts.length} tool{parts.length === 1 ? '' : 's'}
          {usedLabels.length ? `, ${usedLabels.slice(0, 3).join(', ')}` : ''}
          {usedLabels.length > 3 ? '…' : ''}
        </button>
      )}
      {visible.map((part) => (
        <ToolRow
          key={part.toolCallId}
          part={part}
          // All rows are collapsed by default — user expands to drill in.
          defaultOpen={false}
        />
      ))}
    </div>
  );
}

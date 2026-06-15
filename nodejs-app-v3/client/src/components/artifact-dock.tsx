import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import type { Artifact } from '@/hooks/use-artifacts';
import { LottieSparkle } from './lottie-sparkle';

export function ArtifactDock({
  artifact,
  onClose,
  collapsed,
  onToggleCollapsed,
  className,
}: {
  artifact: Artifact;
  onClose: () => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  className?: string;
}) {
  const [iframeReady, setIframeReady] = useState(false);
  const [copied, setCopied] = useState(false);

  // Reset iframe state whenever a new artifact opens
  useEffect(() => {
    setIframeReady(false);
  }, [artifact.id]);

  const onCopy = async () => {
    const text = artifact.srcdoc ?? artifact.href ?? '';
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      // ignore
    }
  };

  // When collapsed, render only a 44px rail with a chevron toggle + a
  // vertical "Artifact" label so the user can still re-open the panel.
  if (collapsed) {
    return (
      <aside
        aria-label={`Artifact (collapsed): ${artifact.title}`}
        className={cn(
          'relative flex flex-col overflow-hidden border-border-1 border-l',
          'bg-[var(--editorial-bg)] transition-[width] duration-[240ms] ease-[var(--ease-snap)]',
          'w-[44px]',
          className,
        )}
      >
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-expanded="false"
          aria-label="Expand artifact panel"
          title="Expand panel"
          className={cn(
            '-translate-x-1/2 absolute top-3.5 left-1/2 z-10',
            'inline-flex h-6 w-6 items-center justify-center rounded-[4px]',
            'cursor-pointer bg-transparent text-fg-3 hover:bg-bg-elev-1 hover:text-fg-1',
            'transition-[background,color] duration-[120ms] ease-[var(--ease-snap)]',
          )}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            {/* chevron points LEFT when collapsed (click to expand outward) */}
            <path d="M10 4l-4 4 4 4" />
          </svg>
        </button>
        <div
          aria-hidden
          className="mx-auto mt-12 rotate-180 font-medium text-[11px] text-fg-3 uppercase tracking-[0.12em] [writing-mode:vertical-rl]"
        >
          Artifact
        </div>
      </aside>
    );
  }

  return (
    <aside
      aria-label={`Artifact: ${artifact.title}`}
      className={cn(
        'flex flex-col overflow-hidden border-border-1 border-l',
        'bg-[var(--editorial-bg)]',
        'animate-[panel-slide-in_300ms_var(--ease-emphasised)]',
        className,
      )}
    >
      {/* Header */}
      <div className="flex shrink-0 items-center gap-2.5 border-border-1 border-b bg-[var(--editorial-bg)] px-[18px] py-2.5">
        {/* Preview indicator (non-interactive — code-view toggle removed) */}
        <span
          aria-hidden
          className="inline-flex h-[26px] w-[28px] items-center justify-center rounded-[4px] bg-white/5 text-fg-1"
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" />
            <circle cx="8" cy="8" r="2" />
          </svg>
        </span>

        <div className="min-w-0 flex-1 truncate font-medium text-[12.5px] text-fg-1">
          {artifact.title}
          {artifact.ext && (
            <span className="font-normal text-fg-3"> · {artifact.ext}</span>
          )}
        </div>

        <button
          type="button"
          onClick={onCopy}
          className="inline-flex items-center gap-1 rounded-[4px] px-2 py-1 text-[11px] text-fg-3 transition-colors duration-[120ms] hover:bg-white/5 hover:text-fg-1"
          aria-label="Copy"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <rect x="4" y="4" width="9" height="10" rx="1" />
            <path d="M11 4V3a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h1" />
          </svg>
          {copied ? 'Copied' : 'Copy'}
        </button>

        {artifact.href && !artifact.srcdoc && (
          <a
            href={artifact.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center rounded-[4px] px-2 py-1 text-fg-3 transition-colors duration-[120ms] hover:bg-white/5 hover:text-fg-1"
            aria-label="Open in new tab"
            title="Open in new tab"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M9 2h5v5M14 2L7 9M12 9v4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h4" />
            </svg>
          </a>
        )}

        {onToggleCollapsed && (
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="inline-flex items-center rounded-[4px] px-2 py-1 text-fg-3 transition-colors duration-[120ms] hover:bg-white/5 hover:text-fg-1"
            aria-label="Collapse artifact panel"
            title="Collapse panel"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              {/* chevron points RIGHT when expanded (click to collapse outward) */}
              <path d="M6 4l4 4-4 4" />
            </svg>
          </button>
        )}

        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center rounded-[4px] px-2 py-1 text-fg-3 transition-colors duration-[120ms] hover:bg-white/5 hover:text-fg-1"
          aria-label="Close artifact"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M3 3l10 10M13 3L3 13" />
          </svg>
        </button>
      </div>

      {/* Body */}
      <div className="relative min-h-0 flex-1 bg-[var(--editorial-bg)]">
        {artifact.kind === 'document' ? (
          <DocumentDownloadCard artifact={artifact} />
        ) : artifact.srcdoc ? (
          <iframe
            key={artifact.id}
            title={artifact.title}
            srcDoc={artifact.srcdoc}
            onLoad={() => setIframeReady(true)}
            className={cn(
              'block h-full w-full border-0 transition-opacity duration-200',
              iframeReady ? 'opacity-100' : 'opacity-0',
            )}
            sandbox="allow-scripts allow-same-origin"
          />
        ) : artifact.href ? (
          <iframe
            key={artifact.id}
            title={artifact.title}
            src={artifact.href}
            onLoad={() => setIframeReady(true)}
            className={cn(
              'block h-full w-full border-0 bg-[var(--editorial-bg)] transition-opacity duration-200',
              iframeReady ? 'opacity-100' : 'opacity-0',
            )}
            sandbox="allow-scripts allow-same-origin allow-popups"
          />
        ) : (
          <ArtifactPlaceholder />
        )}

        {artifact.kind !== 'document' &&
          !iframeReady &&
          (artifact.href || artifact.srcdoc) && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <ArtifactPlaceholder />
            </div>
          )}
      </div>
    </aside>
  );
}

/** Download card for binary office docs (pptx/docx/xlsx/csv/pdf). The dock
 * shows this instead of an iframe — the user clicks the button and the
 * server proxy streams the file with Content-Disposition: attachment. */
function DocumentDownloadCard({ artifact }: { artifact: Artifact }) {
  const fmt = (artifact.format ?? artifact.ext ?? '').toLowerCase();
  const sizeLabel = formatSize(artifact.sizeBytes);
  const appName =
    fmt === 'pptx'
      ? 'PowerPoint'
      : fmt === 'docx'
        ? 'Word'
        : fmt === 'xlsx'
          ? 'Excel'
          : fmt === 'csv'
            ? 'a spreadsheet app'
            : fmt === 'pdf'
              ? 'a PDF viewer'
              : 'its default app';

  return (
    <div className="flex h-full w-full items-center justify-center px-8">
      <div className="flex max-w-[420px] flex-col items-center gap-4 text-center">
        <span
          aria-hidden
          className="inline-flex h-[56px] w-[56px] items-center justify-center rounded-[10px] bg-bg-elev-2 text-fg-1"
        >
          <DocFormatBadge format={fmt} />
        </span>
        <div className="flex flex-col gap-1">
          <div className="font-medium text-[15px] text-fg-1 leading-snug">
            {artifact.title}
          </div>
          <div className="text-[12.5px] text-fg-3">
            {fmt ? `.${fmt}` : 'Document'}
            {sizeLabel && <> · {sizeLabel}</>}
          </div>
        </div>
        {artifact.href && (
          <a
            href={artifact.href}
            download
            className={cn(
              'inline-flex items-center gap-2 rounded-[6px] px-3.5 py-2 text-[12.5px]',
              'bg-clay text-white transition-colors duration-[120ms] hover:bg-clay-soft',
              'cursor-pointer',
            )}
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden
            >
              <path d="M8 2v9M4 7l4 4 4-4M2 14h12" />
            </svg>
            Download
          </a>
        )}
        <p className="max-w-[320px] text-[11.5px] text-fg-3 leading-relaxed">
          Open in {appName} once the file lands in your Downloads.
        </p>
      </div>
    </div>
  );
}

function formatSize(bytes: number | undefined): string | undefined {
  if (typeof bytes !== 'number' || !isFinite(bytes) || bytes <= 0)
    return undefined;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function DocFormatBadge({ format }: { format: string }) {
  const map: Record<string, { label: string; bg: string }> = {
    pptx: { label: 'P', bg: '#c5532a' },
    docx: { label: 'W', bg: '#1f4f9c' },
    xlsx: { label: 'X', bg: '#1f7244' },
    csv: { label: 'X', bg: '#1f7244' },
    pdf: { label: 'PDF', bg: '#a6402e' },
  };
  const cfg = map[format] ?? { label: '·', bg: '#52525b' };
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect x="3" y="3" width="26" height="26" rx="4" fill={cfg.bg} />
      <text
        x="16"
        y="22"
        textAnchor="middle"
        fontFamily="ui-sans-serif, system-ui"
        fontSize={cfg.label.length > 1 ? 9 : 15}
        fontWeight={700}
        fill="#fff"
      >
        {cfg.label}
      </text>
    </svg>
  );
}

function ArtifactPlaceholder() {
  return (
    <div className="flex h-full w-full items-center justify-center text-[12.5px] text-fg-3">
      <div className="flex flex-col items-center gap-2">
        <LottieSparkle variant="thinking" size={18} />
        Loading artifact…
      </div>
    </div>
  );
}

/** Thumbnail chip rendered under an assistant message. */
export function ArtifactThumbChip({
  artifact,
  onOpen,
}: {
  artifact: Artifact;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        'inline-flex items-center gap-3 rounded-[8px] border border-border-2 bg-transparent',
        'max-w-fit cursor-pointer px-3.5 py-2.5 text-left',
        'transition-colors duration-[120ms] hover:border-fg-4 hover:bg-bg-elev-1',
      )}
    >
      <span
        aria-hidden
        className="block h-[36px] w-[56px] shrink-0 rounded-[4px] opacity-60"
        style={{
          background:
            'linear-gradient(135deg, var(--clay) 0%, var(--olive) 100%)',
        }}
      />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="truncate font-medium text-[12.5px] text-fg-1">
          {artifact.title}
        </span>
        <span className="truncate text-[11px] text-clay tracking-[0.02em]">
          Open artifact ↗
        </span>
      </span>
    </button>
  );
}

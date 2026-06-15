import { useState } from 'react';
import { cn } from '@/lib/utils';
import { ToolGlyph } from '@/components/tool-row';
import type {
  ProgressStep,
  ArtifactRow,
  SkillChip,
} from '@/hooks/use-activity-stream';

export function ActivityPanel({
  progress,
  folder,
  skills,
  className,
  onArtifactClick,
  collapsed: controlledCollapsed,
  onToggleCollapsed,
}: {
  progress: ProgressStep[];
  folder: ArtifactRow[];
  skills: SkillChip[];
  className?: string;
  onArtifactClick?: (row: ArtifactRow) => void;
  /** Controlled collapse state. Omit to keep internal state. */
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const collapsed = controlledCollapsed ?? internalCollapsed;
  const toggleCollapsed = onToggleCollapsed ?? (() => setInternalCollapsed((c) => !c));

  return (
    <aside
      aria-label="Agent activity"
      data-collapsed={collapsed ? 'true' : 'false'}
      className={cn(
        'relative hidden shrink-0 flex-col overflow-y-auto xl:flex',
        'border-border-1 border-l bg-bg-canvas',
        // Width animates between full (300px) and rail (44px).
        'transition-[width,padding,gap] duration-[240ms] ease-[var(--ease-snap)]',
        collapsed
          ? 'w-[44px] gap-0 overflow-hidden px-2 py-3.5'
          : 'w-[300px] gap-6 px-[18px] py-[18px]',
        className,
      )}
    >
      {/* Toggle button — top-right when expanded, centered on the rail when collapsed */}
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand activity panel' : 'Collapse activity panel'}
        title={collapsed ? 'Expand panel' : 'Collapse panel'}
        className={cn(
          'absolute top-3.5 z-10 inline-flex h-6 w-6 items-center justify-center',
          'rounded-[4px] bg-transparent text-fg-3 hover:bg-bg-elev-1 hover:text-fg-1',
          'cursor-pointer transition-[background,color,left,right,transform] duration-[120ms] ease-[var(--ease-snap)]',
          collapsed ? '-translate-x-1/2 left-1/2' : 'right-3',
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
          className={cn(
            'transition-transform duration-[120ms] ease-[var(--ease-snap)]',
            collapsed && 'rotate-180',
          )}
        >
          <path d="M6 4l4 4-4 4" />
        </svg>
      </button>

      {/* Vertical "Activity" rail label when collapsed */}
      {collapsed && (
        <div
          aria-hidden
          className={cn(
            'mx-auto mt-12 font-medium text-[11px] text-fg-3 uppercase tracking-[0.12em]',
            'rotate-180 [writing-mode:vertical-rl]',
          )}
        >
          Activity
        </div>
      )}

      {/* Body — fades out when collapsed but keeps its place for animation symmetry */}
      <div
        className={cn(
          'flex min-h-0 flex-1 flex-col gap-6 transition-opacity duration-[120ms] ease-[var(--ease-snap)]',
          collapsed && 'pointer-events-none h-0 overflow-hidden opacity-0',
        )}
      >
        <ActSection title="Progress">
          {progress.length === 0 ? (
            <p className='m-0 text-[12.5px] text-fg-3'>
              No active task. Send a message to begin.
            </p>
          ) : (
            <div className="flex flex-col">
              {progress.map((step, i) => (
                <ProgressStepRow key={step.id || i} step={step} index={i} />
              ))}
            </div>
          )}
        </ActSection>

        <ActSection title="Working folder">
          {folder.length === 0 ? (
            <p className='m-0 text-[12.5px] text-fg-3'>No artifacts yet.</p>
          ) : (
            <div className="flex flex-col">
              {folder.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => onArtifactClick?.(row)}
                  className='flex cursor-pointer items-center gap-2 py-1.5 text-left text-[12.5px] text-fg-2 transition-colors duration-[120ms] hover:text-fg-1'
                >
                  <span
                    aria-hidden
                    className='inline-flex h-[14px] w-[14px] shrink-0 items-center justify-center text-fg-3'
                  >
                    <FolderGlyph glyph={row.glyph} ext={row.ext} />
                  </span>
                  <span className='flex-1 truncate'>{row.name}</span>
                  <span aria-hidden className='shrink-0 text-[12.5px] text-fg-3'>
                    ›
                  </span>
                </button>
              ))}
            </div>
          )}
        </ActSection>

        <ActSection title="Context">
          <div className='mb-2 font-medium text-[11px] text-fg-3 uppercase tracking-[0.08em]'>
            Connectors
          </div>
          {skills.length === 0 ? (
            <p className='m-0 text-[12.5px] text-fg-3'>
              Skills appear as the agent uses them.
            </p>
          ) : (
            <div className='flex flex-col items-start gap-1.5'>
              {skills.map((skill) => (
                <span
                  key={skill.name}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-[6px] border border-border-1 bg-bg-elev-1',
                    'px-2.5 py-1.5 text-[12.5px] text-fg-1',
                    'animate-[chip-pop-in_240ms_var(--ease-spring)]',
                  )}
                >
                  <span
                    aria-hidden
                    className="inline-flex h-[14px] w-[14px] shrink-0 items-center justify-center rounded-[3px] bg-bg-elev-2 text-[10px] text-fg-3"
                  >
                    <ToolGlyph glyph={skill.glyph} />
                  </span>
                  {skill.name}
                </span>
              ))}
            </div>
          )}
        </ActSection>
      </div>

      {/* Socials — pinned to the bottom-left of the panel when expanded */}
      {!collapsed && <PanelSocials />}
    </aside>
  );
}

const SOCIAL_LINKS: { label: string; href: string; icon: React.ReactNode }[] = [
  {
    label: 'Website — resonance-analytics.com',
    href: 'https://www.resonance-analytics.com/',
    icon: (
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <circle cx="12" cy="12" r="10" />
        <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
        <path d="M2 12h20" />
      </svg>
    ),
  },
  {
    label: 'YouTube — @resonanceanalytics',
    href: 'https://www.youtube.com/@resonanceanalytics',
    icon: (
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <path d="M9 9.003a1 1 0 0 1 1.517-.859l4.997 2.997a1 1 0 0 1 0 1.718l-4.997 2.997A1 1 0 0 1 9 14.996z" />
      </svg>
    ),
  },
  {
    label: 'LinkedIn — rathes-waran',
    href: 'https://www.linkedin.com/in/rathes-waran/',
    icon: (
      <svg width="16" height="16" viewBox="0 0 448 512" fill="currentColor" aria-hidden>
        <path d="M416 32H31.9C14.3 32 0 46.5 0 64.3v383.4C0 465.5 14.3 480 31.9 480H416c17.6 0 32-14.5 32-32.3V64.3c0-17.8-14.4-32.3-32-32.3zM135.4 416H69V202.2h66.5V416zm-33.2-243c-21.3 0-38.5-17.3-38.5-38.5S80.9 96 102.2 96c21.2 0 38.5 17.3 38.5 38.5 0 21.3-17.2 38.5-38.5 38.5zm282.1 243h-66.4V312c0-24.8-.5-56.7-34.5-56.7-34.6 0-39.9 27-39.9 54.9V416h-66.4V202.2h63.7v29.2h.9c8.9-16.8 30.6-34.5 62.9-34.5 67.2 0 79.7 44.3 79.7 101.9V416z" />
      </svg>
    ),
  },
];

function PanelSocials() {
  return (
    <div className='mt-auto flex items-center gap-1 border-border-1 border-t pt-3'>
      {SOCIAL_LINKS.map((s) => (
        <a
          key={s.href}
          href={s.href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={s.label}
          title={s.label}
          className='inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-fg-3 transition-colors duration-[120ms] hover:bg-bg-elev-1 hover:text-fg-1'
        >
          {s.icon}
        </a>
      ))}
    </div>
  );
}

function ActSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h5 className='m-0 mb-3 flex items-center gap-1.5 font-medium text-[14px] text-fg-1'>
        {title}
        <span aria-hidden className='text-[12.5px] text-fg-3'>⌄</span>
      </h5>
      {children}
    </section>
  );
}

function ProgressStepRow({ step, index }: { step: ProgressStep; index: number }) {
  return (
    <div className="flex items-start gap-[11px] py-1.5 text-[12.5px] leading-snug">
      <span
        className={cn(
          'inline-flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full font-medium text-[11px]',
          'tabular-nums transition-[background,color,border-color] duration-[240ms] ease-[var(--ease-spring)]',
          step.state === 'pending' && 'border-[1.5px] border-border-2 bg-transparent text-fg-3',
          step.state === 'active' && 'border-[1.5px] border-clay bg-clay text-white',
          step.state === 'done' && 'border-[1.5px] border-olive bg-transparent text-olive',
        )}
        aria-hidden
      >
        {step.state === 'done' ? '✓' : index + 1}
      </span>
      <span
        className={cn(
          step.state === 'pending' && 'text-fg-3',
          step.state === 'active' && 'font-medium text-fg-1',
          step.state === 'done' && 'text-fg-3 line-through decoration-[1px] decoration-fg-4',
        )}
      >
        {step.label}
      </span>
    </div>
  );
}

/**
 * File-type icon for the working-folder row. SVG markup matches the
 * Inferred Design v2 handoff:
 *   - ipynb / py / databricks notebook → two-tone Python logo silhouette
 *   - html                              → globe (sphere + equator + meridians)
 *   - md                                → "MD" badge in a rounded rect (currentColor)
 *   - xlsx                              → green "X" badge
 *   - docx                              → blue "W" badge
 *   - pptx                              → orange "P" badge
 * Falls back to the raw glyph string for anything else.
 */
function FolderGlyph({ glyph, ext }: { glyph: string; ext?: string }) {
  const e = ext?.toLowerCase();
  if (e === 'ipynb' || e === 'py' || e === 'nb') {
    return (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
        <path
          fill="#5fa6dd"
          d="M7.5 1.5c-2 0-2 1-2 2v1h2.4v.4H3.6c-1.2 0-2 .8-2 2v1.6c0 1.2.8 2 2 2h1V9.4c0-1.2.8-2 2-2h3.4c1 0 1.8-.8 1.8-1.8V3.5c0-1-1-2-2.2-2H7.5zm-1 1.1a.55.55 0 1 1 0 1.1.55.55 0 0 1 0-1.1z"
        />
        <path
          fill="#ffd44a"
          d="M8.5 14.5c2 0 2-1 2-2v-1H8.1v-.4h4.3c1.2 0 2-.8 2-2V7.5c0-1.2-.8-2-2-2h-1V6.6c0 1.2-.8 2-2 2H6c-1 0-1.8.8-1.8 1.8v1.7c0 1 1 2 2.2 2h2.1zm1-1.1a.55.55 0 1 1 0-1.1.55.55 0 0 1 0 1.1z"
        />
      </svg>
    );
  }
  if (e === 'html' || e === 'htm') {
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.3}
        strokeLinecap="round"
        aria-hidden
      >
        <circle cx="8" cy="8" r="6" />
        <ellipse cx="8" cy="8" rx="3" ry="6" />
        <path d="M2 8h12" />
      </svg>
    );
  }
  if (e === 'md' || e === 'markdown') {
    return (
      <svg
        width="16"
        height="12"
        viewBox="0 0 22 14"
        fill="none"
        aria-hidden
      >
        <rect
          x="0.6"
          y="0.6"
          width="20.8"
          height="12.8"
          rx="2"
          stroke="currentColor"
          strokeWidth={1.2}
        />
        <text
          x="11"
          y="9.6"
          textAnchor="middle"
          fontFamily="ui-monospace,SFMono-Regular,Menlo,monospace"
          fontSize="6.6"
          fontWeight={600}
          fill="currentColor"
          letterSpacing="0.4"
        >
          MD
        </text>
      </svg>
    );
  }
  if (e === 'xlsx' || e === 'xls' || e === 'csv' || e === 'tsv') {
    return (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
        <rect x="2" y="2" width="12" height="12" rx="1.5" fill="#1f7244" />
        <text
          x="8"
          y="11"
          textAnchor="middle"
          fontFamily="ui-sans-serif,system-ui"
          fontSize="7"
          fontWeight={700}
          fill="#fff"
        >
          X
        </text>
      </svg>
    );
  }
  if (e === 'docx' || e === 'doc') {
    return (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
        <rect x="2" y="2" width="12" height="12" rx="1.5" fill="#1f4f9c" />
        <text
          x="8"
          y="11"
          textAnchor="middle"
          fontFamily="ui-sans-serif,system-ui"
          fontSize="7"
          fontWeight={700}
          fill="#fff"
        >
          W
        </text>
      </svg>
    );
  }
  if (e === 'pptx' || e === 'ppt') {
    return (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
        <rect x="2" y="2" width="12" height="12" rx="1.5" fill="#c5532a" />
        <text
          x="8"
          y="11"
          textAnchor="middle"
          fontFamily="ui-sans-serif,system-ui"
          fontSize="7"
          fontWeight={700}
          fill="#fff"
        >
          P
        </text>
      </svg>
    );
  }
  return <ToolGlyph glyph={glyph} />;
}

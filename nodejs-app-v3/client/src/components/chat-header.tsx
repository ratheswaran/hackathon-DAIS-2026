import { useNavigate } from 'react-router-dom';

import { SidebarToggle } from '@/components/sidebar-toggle';
import { MapPinned, TriangleAlert, Waypoints } from 'lucide-react';
import { useConfig } from '@/hooks/use-config';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { CloudOffIcon } from './icons';
import { cn } from '../lib/utils';
import { Skeleton } from './ui/skeleton';

const DOCS_URL =
  'https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app';
const OBO_DOCS_URL =
  'https://docs.databricks.com/aws/en/generative-ai/agent-framework/chat-app#enable-user-authorization';

export type StatusChipKind = 'idle' | 'working' | 'done' | 'error';

function StatusChip({ kind }: { kind: StatusChipKind }) {
  const labels: Record<StatusChipKind, string> = {
    idle: 'Idle',
    working: 'Working',
    done: 'Done',
    error: 'Error',
  };
  const dotColors: Record<StatusChipKind, string> = {
    idle: 'bg-fg-3',
    working: 'bg-clay',
    done: 'bg-olive',
    error: 'bg-[var(--danger)]',
  };
  const isLive = kind === 'working';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border-1 bg-bg-elev-1 px-2.5 py-1 font-medium text-[11px]',
        kind === 'working' && 'text-fg-1',
        kind !== 'working' && 'text-fg-2',
      )}
      role="status"
      aria-live="polite"
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          dotColors[kind],
          isLive && 'animate-[sparkle-pulse_1.6s_ease-in-out_infinite]',
        )}
        aria-hidden
      />
      <span className={cn(isLive && 'shimmer-text')}>{labels[kind]}</span>
    </span>
  );
}

function OboScopeBanner({ missingScopes }: { missingScopes: string[] }) {
  if (missingScopes.length === 0) return null;
  return (
    <div className="w-full border-[var(--border-warning)] border-b bg-[var(--background-warning)] px-4 py-2.5">
      <div className="flex items-center gap-2">
        <TriangleAlert className="h-4 w-4 shrink-0 text-clay" />
        <p className="text-[12.5px] text-fg-1">
          This endpoint requires on-behalf-of user authorization. Add these
          scopes to your app: <strong>{missingScopes.join(', ')}</strong>.{' '}
          <a
            href={OBO_DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-clay underline hover:text-clay-soft"
          >
            Learn more
          </a>
        </p>
      </div>
    </div>
  );
}

export function ChatHeader({
  title,
  empty,
  isLoadingTitle,
  statusChip = 'idle',
}: {
  title?: string;
  empty?: boolean;
  isLoadingTitle?: boolean;
  statusChip?: StatusChipKind;
}) {
  const navigate = useNavigate();
  const { chatHistoryEnabled, oboMissingScopes } = useConfig();

  return (
    <>
      <header
        className={cn(
          'flex h-[56px] shrink-0 items-center gap-2.5 border-border-1 border-b bg-bg-canvas px-5',
          empty && 'border-b-transparent',
        )}
      >
        {/* Mobile sidebar toggle */}
        <div className="md:hidden">
          <SidebarToggle forceOpenIcon />
        </div>

        {(title || isLoadingTitle) && (
          <h4 className="max-w-[60ch] truncate font-medium text-[16px] text-fg-1">
            {isLoadingTitle ? (
              <Skeleton className="h-5 w-32 bg-bg-elev-2" />
            ) : (
              title
            )}
          </h4>
        )}

        <div className="ml-auto flex items-center gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href="/india_medical_deserts.html"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-[6px] border border-border-1 bg-bg-elev-1 px-2 py-1 text-[11px] text-fg-2 transition-colors duration-[120ms] hover:text-fg-1"
                >
                  <MapPinned className="h-3 w-3" />
                  <span className="hidden sm:inline">Medical deserts</span>
                </a>
              </TooltipTrigger>
              <TooltipContent>
                <p>Open the India medical-desert map (district access gaps).</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <a
                  href="/api/skill_graph/explorer.html"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-[6px] border border-border-1 bg-bg-elev-1 px-2 py-1 text-[11px] text-fg-2 transition-colors duration-[120ms] hover:text-fg-1"
                >
                  <Waypoints className="h-3 w-3" />
                  <span className="hidden sm:inline">Knowledge graph</span>
                </a>
              </TooltipTrigger>
              <TooltipContent>
                <p>Explore the skills knowledge graph the agent plans with.</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {!chatHistoryEnabled && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <a
                    href={DOCS_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 rounded-[6px] border border-border-1 bg-bg-elev-1 px-2 py-1 text-[11px] text-fg-2 transition-colors duration-[120ms] hover:text-fg-1"
                  >
                    <CloudOffIcon className="h-3 w-3" />
                    <span className="hidden sm:inline">Ephemeral</span>
                  </a>
                </TooltipTrigger>
                <TooltipContent>
                  <p>
                    Chat history disabled — conversations are not saved. Click
                    to learn more.
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          <StatusChip kind={statusChip} />

          {/* Mobile new-chat shortcut */}
          <button
            type="button"
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-1 rounded-[6px] bg-clay px-2.5 py-1 font-medium text-[12.5px] text-white transition-colors duration-[120ms] hover:bg-clay-soft md:hidden"
          >
            <span aria-hidden>+</span>
            New
          </button>
        </div>
      </header>

      <OboScopeBanner missingScopes={oboMissingScopes} />
    </>
  );
}

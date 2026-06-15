import { useNavigate } from 'react-router-dom';

import { SidebarHistory } from '@/components/sidebar-history';
import { SidebarUserNav } from '@/components/sidebar-user-nav';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  useSidebar,
} from '@/components/ui/sidebar';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { ClientSession } from '@chat-template/auth';
import { cn } from '@/lib/utils';

export function AppSidebar({
  user,
  preferredUsername,
}: {
  user: ClientSession['user'] | undefined;
  preferredUsername: string | null;
}) {
  const navigate = useNavigate();
  const { setOpenMobile, open, openMobile, isMobile, toggleSidebar } = useSidebar();
  const effectiveOpen = open || (isMobile && openMobile);

  return (
    <Sidebar
      collapsible="icon"
      className='bg-sidebar text-sidebar-foreground group-data-[side=left]:border-r-0'
    >
      {/* Header: brand + collapse toggle */}
      <SidebarHeader
        className={cn(
          'h-[44px] flex-row items-center gap-2 px-3 py-0',
          effectiveOpen ? 'justify-between' : 'justify-center',
        )}
      >
        {effectiveOpen && (
          <button
            type="button"
            onClick={() => {
              setOpenMobile(false);
              navigate('/');
            }}
            className="flex items-center gap-2 overflow-hidden text-left"
            aria-label="Home"
          >
            <img
              src="/ra-brandmark.svg"
              alt=""
              aria-hidden
              width={18}
              height={18}
              className='shrink-0'
            />
            <span className='truncate font-medium text-[14px] text-fg-1 tracking-[0.02em]'>
              The Pudding Agent
            </span>
          </button>
        )}

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={toggleSidebar}
              className='inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-fg-3 transition-colors duration-[120ms] hover:bg-bg-elev-1 hover:text-fg-1'
              aria-label={effectiveOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            >
              <ChevronCollapseGlyph open={effectiveOpen} />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" style={{ display: open ? 'none' : 'block' }}>
            {effectiveOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          </TooltipContent>
        </Tooltip>
      </SidebarHeader>

      {/* New task button */}
      <div className="px-2.5 pt-2 pb-3">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => {
                setOpenMobile(false);
                navigate('/');
              }}
              className={cn(
                'group flex w-full items-center gap-2 rounded-[6px] border border-border-2 bg-transparent px-2.5 py-2 text-[13px] text-fg-1',
                'cursor-pointer transition-colors duration-[120ms] hover:bg-bg-elev-1',
                !effectiveOpen && 'justify-center px-1.5',
              )}
            >
              <span aria-hidden className='font-medium text-[14px] text-clay leading-none'>
                +
              </span>
              {effectiveOpen && <span>New task</span>}
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" style={{ display: open ? 'none' : 'block' }}>
            New task
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Recents */}
      <SidebarContent>
        {effectiveOpen && (
          <div className="px-2.5">
            <div className='mb-1.5 px-2 font-medium text-[11px] text-fg-3 uppercase tracking-[0.08em]'>
              Recents
            </div>
            <SidebarHistory user={user} />
          </div>
        )}
      </SidebarContent>

      {/* User nav */}
      <SidebarFooter className='border-border-1 border-t px-2.5 pt-2.5 pb-2.5'>
        {user && (
          <SidebarUserNav user={user} preferredUsername={preferredUsername} />
        )}
      </SidebarFooter>
    </Sidebar>
  );
}

function ChevronCollapseGlyph({ open }: { open: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect x="2" y="3" width="12" height="10" rx="1.5" />
      {open ? (
        <path d="M9 6l-2 2 2 2" />
      ) : (
        <path d="M7 6l2 2-2 2" />
      )}
      <line x1="6" y1="3" x2="6" y2="13" />
    </svg>
  );
}

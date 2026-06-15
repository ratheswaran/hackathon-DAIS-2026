import { Outlet } from 'react-router-dom';
import { AppSidebar } from '@/components/app-sidebar';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import { useSession } from '@/contexts/SessionContext';

export default function ChatLayout() {
  const { session, loading } = useSession();
  const isCollapsed = localStorage.getItem('sidebar:state') !== 'true';

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg-canvas text-fg-3">
        Loading…
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="flex h-screen items-center justify-center bg-bg-canvas">
        <div className="flex flex-col items-center gap-6">
          <div className="flex items-center gap-2 text-[14px] text-fg-2 tracking-[0.02em]">
            <img src="/ra-brandmark.svg" alt="" aria-hidden width={18} height={18} className='shrink-0' />
            The Pudding Agent
          </div>
          <div className="flex w-[340px] flex-col items-center gap-3.5 rounded-[12px] border border-border-1 bg-bg-elev-1 p-10 shadow-[var(--shadow-elev)]">
            <div className="flex h-12 w-12 items-center justify-center rounded-[8px] border border-border-1 bg-bg-elev-2 text-clay">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
                <rect
                  x="5"
                  y="11"
                  width="14"
                  height="9"
                  rx="1.5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                />
                <path
                  d="M8 11V8a4 4 0 018 0v3"
                  stroke="currentColor"
                  strokeWidth="1.5"
                />
                <circle cx="12" cy="15.5" r="1.2" fill="currentColor" />
              </svg>
            </div>
            <h3 className='font-medium text-[16px] text-fg-1'>
              Authentication required
            </h3>
            <p className="text-center text-[12.5px] text-fg-2 leading-[1.5]">
              Sign in to your workspace to continue.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const preferredUsername = session.user.preferredUsername ?? null;

  return (
    <SidebarProvider defaultOpen={!isCollapsed}>
      <AppSidebar user={session.user} preferredUsername={preferredUsername} />
      <SidebarInset className="h-svh overflow-hidden bg-bg-canvas">
        <div className="flex flex-1 flex-col overflow-hidden bg-bg-canvas">
          <Outlet />
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

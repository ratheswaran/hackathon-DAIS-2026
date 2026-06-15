import type { DataUIPart, LanguageModelUsage, UIMessageChunk } from 'ai';
import { useChat } from '@ai-sdk/react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSWRConfig } from 'swr';
import { ChatHeader } from '@/components/chat-header';
import { fetchWithErrorHandlers, generateUUID } from '@/lib/utils';
import { MultimodalInput } from './multimodal-input';
import { Messages } from './messages';
import type {
  Attachment,
  ChatMessage,
  CustomUIDataTypes,
  FeedbackMap,
  VisibilityType,
} from '@chat-template/core';
import { unstable_serialize } from 'swr/infinite';
import { getChatHistoryPaginationKey } from './sidebar-history';
import { toast } from './toast';
import { useSearchParams } from 'react-router-dom';
import { useChatVisibility } from '@/hooks/use-chat-visibility';
import { ChatSDKError } from '@chat-template/core/errors';
import { useDataStream } from './data-stream-provider';
import { isCredentialErrorMessage } from '@/lib/oauth-error-utils';
import { ChatTransport } from '../lib/ChatTransport';
import type { ClientSession } from '@chat-template/auth';
import { softNavigateToChatId } from '@/lib/navigation';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { Greeting } from './greeting';
import { ActivityPanel } from './activity-panel';
import { useActivityStream } from '@/hooks/use-activity-stream';
import { useArtifacts, useArtifactDock } from '@/hooks/use-artifacts';
import { ArtifactDock } from './artifact-dock';
import { cn } from '@/lib/utils';

export function Chat({
  id,
  initialMessages,
  initialChatModel,
  initialVisibilityType,
  isReadonly,
  initialLastContext,
  feedback = {},
  title,
}: {
  id: string;
  initialMessages: ChatMessage[];
  initialChatModel: string;
  initialVisibilityType: VisibilityType;
  isReadonly: boolean;
  session: ClientSession;
  initialLastContext?: LanguageModelUsage;
  feedback?: FeedbackMap;
  title?: string;
}) {
  const { visibilityType } = useChatVisibility({
    chatId: id,
    initialVisibilityType,
  });

  const { mutate } = useSWRConfig();
  const { setDataStream } = useDataStream();
  const { chatHistoryEnabled } = useAppConfig();

  const [input, setInput] = useState<string>('');
  const [_usage, setUsage] = useState<LanguageModelUsage | undefined>(
    initialLastContext,
  );

  const [lastPart, setLastPart] = useState<UIMessageChunk | undefined>();
  const lastPartRef = useRef<UIMessageChunk | undefined>(lastPart);
  lastPartRef.current = lastPart;

  const resumeAttemptCountRef = useRef(0);
  const maxResumeAttempts = 3;

  const abortController = useRef<AbortController | null>(new AbortController());
  useEffect(() => {
    return () => {
      abortController.current?.abort('ABORT_SIGNAL');
    };
  }, []);

  const fetchWithAbort = useMemo(() => {
    return async (input: RequestInfo | URL, init?: RequestInit) => {
      const signal = abortController.current?.signal;
      return fetchWithErrorHandlers(input, { ...init, signal });
    };
  }, []);

  const stop = useCallback(() => {
    abortController.current?.abort('USER_ABORT_SIGNAL');
  }, []);

  const isNewChat = initialMessages.length === 0;
  const didFetchHistoryOnNewChat = useRef(false);
  const fetchChatHistory = useCallback(() => {
    mutate(unstable_serialize(getChatHistoryPaginationKey));
  }, [mutate]);

  const [streamTitle, setStreamTitle] = useState<string | undefined>();
  const [titlePending, setTitlePending] = useState(false);
  const displayTitle = title ?? streamTitle;

  const {
    messages,
    setMessages,
    sendMessage,
    status,
    resumeStream,
    clearError,
    addToolApprovalResponse,
    regenerate,
  } = useChat<ChatMessage>({
    id,
    messages: initialMessages,
    experimental_throttle: 100,
    generateId: generateUUID,
    resume: id !== undefined && initialMessages.length > 0,
    transport: new ChatTransport({
      onStreamPart: (part) => {
        if (isNewChat && !didFetchHistoryOnNewChat.current) {
          fetchChatHistory();
          if (chatHistoryEnabled) {
            setTitlePending(true);
          }
          didFetchHistoryOnNewChat.current = true;
        }
        resumeAttemptCountRef.current = 0;
        setLastPart(part);
      },
      api: '/api/chat',
      fetch: fetchWithAbort,
      prepareSendMessagesRequest({ messages, id, body }) {
        const lastMessage = messages.at(-1);
        const isUserMessage = lastMessage?.role === 'user';
        const needsPreviousMessages = !chatHistoryEnabled || !isUserMessage;

        return {
          body: {
            id,
            ...(isUserMessage ? { message: lastMessage } : {}),
            selectedChatModel: initialChatModel,
            selectedVisibilityType: visibilityType,
            nextMessageId: generateUUID(),
            ...(needsPreviousMessages
              ? {
                  previousMessages: isUserMessage
                    ? messages.slice(0, -1)
                    : messages,
                }
              : {}),
            ...body,
          },
        };
      },
      prepareReconnectToStreamRequest({ id }) {
        return {
          api: `/api/chat/${id}/stream`,
          credentials: 'include',
        };
      },
    }),
    onData: (dataPart) => {
      setDataStream((ds) =>
        ds ? [...ds, dataPart as DataUIPart<CustomUIDataTypes>] : [],
      );
      if (dataPart.type === 'data-usage') {
        setUsage(dataPart.data as LanguageModelUsage);
      }
      if (dataPart.type === 'data-title') {
        setStreamTitle(dataPart.data as string);
        setTitlePending(false);
        fetchChatHistory();
      }
    },
    onFinish: ({ isAbort, isDisconnect, isError, messages: finishedMessages }) => {
      didFetchHistoryOnNewChat.current = false;
      setTitlePending(false);

      if (isAbort) {
        console.log('[Chat onFinish] Stream was aborted by user, not resuming');
        fetchChatHistory();
        return;
      }

      const lastMessage = finishedMessages?.at(-1);
      const hasOAuthError = lastMessage?.parts?.some(
        (part) =>
          part.type === 'data-error' &&
          typeof part.data === 'string' &&
          isCredentialErrorMessage(part.data),
      );

      if (hasOAuthError) {
        console.log('[Chat onFinish] OAuth credential error detected, not resuming');
        fetchChatHistory();
        clearError();
        return;
      }

      const streamIncomplete = lastPartRef.current?.type !== 'finish';
      const shouldResume =
        streamIncomplete &&
        (isDisconnect || isError || lastPartRef.current === undefined);

      if (shouldResume && resumeAttemptCountRef.current < maxResumeAttempts) {
        console.log(
          '[Chat onFinish] Resuming stream. Attempt:',
          resumeAttemptCountRef.current + 1,
        );
        resumeAttemptCountRef.current++;
        queueMicrotask(() => {
          resumeStream();
        });
      } else {
        if (resumeAttemptCountRef.current >= maxResumeAttempts) {
          console.warn('[Chat onFinish] Max resume attempts reached');
        }
        fetchChatHistory();
      }
    },
    onError: (error) => {
      console.log('[Chat onError] Error occurred:', error);
      if (error instanceof ChatSDKError) {
        toast({ type: 'error', description: error.message });
      } else {
        console.warn('[Chat onError] Error during streaming:', error.message);
      }
    },
  });

  const [searchParams] = useSearchParams();
  const query = searchParams.get('query');
  const [hasAppendedQuery, setHasAppendedQuery] = useState(false);

  useEffect(() => {
    if (query && !hasAppendedQuery) {
      sendMessage({
        role: 'user' as const,
        parts: [{ type: 'text', text: query }],
      });
      setHasAppendedQuery(true);
      softNavigateToChatId(id, chatHistoryEnabled);
    }
  }, [query, sendMessage, hasAppendedQuery, id, chatHistoryEnabled]);

  const [attachments, setAttachments] = useState<Array<Attachment>>([]);

  // Activity rail derivation (read-only over messages)
  const { progress, folder, skills } = useActivityStream(messages, status);
  const artifacts = useArtifacts(messages);
  const dock = useArtifactDock(artifacts);

  // Artifact panel collapse — separate from `dock.isOpen`. The dock can be
  // open (an artifact is selected) but visually collapsed to a 44px rail
  // when the user clicks the chevron. Reset whenever a different artifact
  // is opened so a freshly auto-opened panel always starts expanded.
  const [artifactCollapsed, setArtifactCollapsed] = useState(false);
  useEffect(() => {
    setArtifactCollapsed(false);
  }, [dock.active?.id]);

  // Activity panel collapse — controlled so it can coexist with the artifact
  // dock as a 44px rail when an artifact is open. Defaults to expanded;
  // auto-collapses on the dock-open transition (to make room), auto-expands
  // when the dock closes. The user can still toggle manually mid-session.
  const [activityCollapsed, setActivityCollapsed] = useState(false);
  const prevDockOpenRef = useRef(dock.isOpen);
  useEffect(() => {
    if (dock.isOpen && !prevDockOpenRef.current) setActivityCollapsed(true);
    else if (!dock.isOpen && prevDockOpenRef.current) setActivityCollapsed(false);
    prevDockOpenRef.current = dock.isOpen;
  }, [dock.isOpen]);

  const onArtifactRowClick = useCallback(
    (row: { id: string; href?: string }) => {
      // Activity row ids fall in two buckets:
      //   (a) chart/infographic/document — have an Artifact entry in useArtifacts
      //       → open the dock. Strip the row's `<kind>:` prefix and exact-match
      //       the artifact id.
      //   (b) notebook / raw-path rows (sub-agent created, surfaced via
      //       scanTextForArtifacts) — NOT in useArtifacts because they're not
      //       iframe-renderable artifacts → open the href in a new tab so the
      //       user actually lands somewhere (the notebook in Databricks).
      const stripped = row.id.replace(/^(chart|infographic|document):/, '');
      const match =
        artifacts.find((a) => a.id === stripped) ??
        artifacts.find((a) => a.id === row.id) ??
        artifacts.find((a) => row.id.endsWith(a.id));
      if (match) {
        dock.open(match.id);
      } else if (row.href) {
        // Fall back to opening the underlying URL — works for notebooks
        // (workspace `/editor/notebooks/<id>` URLs) and any other non-dockable
        // row that has an href.
        window.open(row.href, '_blank', 'noopener,noreferrer');
      } else if (typeof window !== 'undefined') {
        console.warn(
          '[activity-panel] no artifact matched for row',
          row.id,
          'candidates:',
          artifacts.map((a) => a.id),
        );
      }
    },
    [artifacts, dock],
  );

  const inputElement = (
    <MultimodalInput
      chatId={id}
      input={input}
      setInput={setInput}
      status={status}
      stop={stop}
      attachments={attachments}
      setAttachments={setAttachments}
      messages={messages}
      setMessages={setMessages}
      sendMessage={sendMessage}
      selectedVisibilityType={visibilityType}
    />
  );

  const status_chip = (() => {
    if (status === 'submitted' || status === 'streaming') return 'working';
    if (status === 'error') return 'error';
    if (messages.length === 0) return 'idle';
    return 'done';
  })();

  // 3-pane shell: chat | activity | (optional) artifact dock
  // The dock takes the activity panel's slot when open and pushes activity off
  // (activity panel hidden under xl when dock is open to keep things readable).
  return (
    <div className="flex h-dvh w-full min-w-0 bg-bg-canvas">
      {/* Chat column */}
      <div
        className={cn(
          'relative flex min-w-0 flex-1 flex-col overflow-hidden bg-bg-canvas',
        )}
      >
        <ChatHeader
          title={displayTitle}
          isLoadingTitle={titlePending && !displayTitle}
          empty={messages.length === 0}
          statusChip={status_chip}
        />

        {messages.length === 0 ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-4">
            <div className="m-auto flex w-full max-w-[720px] flex-col">
              <Greeting />
              {!isReadonly && (
                <div className="mt-2">{inputElement}</div>
              )}
            </div>
          </div>
        ) : (
          <>
            <Messages
              status={status}
              messages={messages}
              setMessages={setMessages}
              addToolApprovalResponse={addToolApprovalResponse}
              regenerate={regenerate}
              sendMessage={sendMessage}
              isReadonly={isReadonly}
              selectedModelId={initialChatModel}
              feedback={feedback}
              artifacts={artifacts}
              onOpenArtifact={(a) => {
                if (typeof window !== 'undefined') {
                  console.warn('[chip-click] open artifact', a.id, 'kind=', a.kind);
                }
                dock.open(a.id);
              }}
            />

            <div className='sticky bottom-0 z-10 mx-auto w-full max-w-[760px] border-border-1 border-t bg-bg-canvas px-4 pt-3 pb-5'>
              {!isReadonly && inputElement}
            </div>
          </>
        )}
      </div>

      {/* Right rail(s): activity panel always rendered while there's a thread,
          artifact dock appended to its right when an artifact is open. Each
          panel handles its own collapse animation so they can coexist. */}
      {messages.length > 0 && (
        <ActivityPanel
          progress={progress}
          folder={folder}
          skills={skills}
          onArtifactClick={onArtifactRowClick}
          collapsed={activityCollapsed}
          onToggleCollapsed={() => setActivityCollapsed((c) => !c)}
        />
      )}

      {dock.isOpen && dock.active && (
        <div
          className={cn(
            'hidden shrink-0 transition-[width] duration-[240ms] ease-[var(--ease-snap)] lg:flex',
            artifactCollapsed && 'w-[44px]',
          )}
          // Tailwind JIT silently drops `w-[min(57vw,720px)]` (the comma inside
          // the calc trips the parser), so the dock fell back to 0 / 44px. Set
          // the expanded width as an inline style — the only path that survives
          // bundling and matches the design's chat-shrink-to-43% behaviour.
          style={artifactCollapsed ? undefined : { width: 'min(57vw, 720px)' }}
        >
          <ArtifactDock
            artifact={dock.active}
            onClose={dock.close}
            collapsed={artifactCollapsed}
            onToggleCollapsed={() => setArtifactCollapsed((c) => !c)}
            className="flex-1"
          />
        </div>
      )}
    </div>
  );
}

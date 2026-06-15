import React, { memo, useState, type Dispatch, type SetStateAction } from 'react';
import { Response } from './elements/response';
import {
  McpTool,
  McpToolHeader,
  McpToolContent,
  McpToolInput,
  McpApprovalActions,
} from './elements/mcp-tool';
import { ToolOutput, type ToolState } from './elements/tool';
import { MessageActions } from './message-actions';
import { PreviewAttachment } from './preview-attachment';
import equal from 'fast-deep-equal';
import { cn, sanitizeText } from '@/lib/utils';
import { MessageEditor } from './message-editor';
import { MessageReasoning } from './message-reasoning';
import type { UseChatHelpers } from '@ai-sdk/react';
import type { ChatMessage, Feedback } from '@chat-template/core';
import { useDataStream } from './data-stream-provider';
import {
  createMessagePartSegments,
  formatNamePart,
  isNamePart,
  joinMessagePartSegments,
} from './databricks-message-part-transformers';
import { MessageError } from './message-error';
import { MessageOAuthError } from './message-oauth-error';
import { isCredentialErrorMessage } from '@/lib/oauth-error-utils';
import { Streamdown } from 'streamdown';
import { useApproval } from '@/hooks/use-approval';
import { ToolRowWindow, type RowToolPart } from './tool-row';
import { SparkleTicker } from './sparkle-ticker';
import { ArtifactThumbChip } from './artifact-dock';
import type { Artifact } from '@/hooks/use-artifacts';

const PurePreviewMessage = ({
  message,
  allMessages,
  isLoading,
  setMessages,
  addToolApprovalResponse,
  sendMessage,
  regenerate,
  isReadonly,
  requiresScrollPadding,
  initialFeedback,
  artifactsByMessage,
  onOpenArtifact,
}: {
  message: ChatMessage;
  allMessages: ChatMessage[];
  isLoading: boolean;
  setMessages: UseChatHelpers<ChatMessage>['setMessages'];
  addToolApprovalResponse: UseChatHelpers<ChatMessage>['addToolApprovalResponse'];
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  regenerate: UseChatHelpers<ChatMessage>['regenerate'];
  isReadonly: boolean;
  requiresScrollPadding: boolean;
  initialFeedback?: Feedback;
  artifactsByMessage?: Record<string, Artifact[]>;
  onOpenArtifact?: (artifact: Artifact) => void;
}) => {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [showErrors, setShowErrors] = useState(false);

  const { submitApproval, isSubmitting, pendingApprovalId } = useApproval({
    addToolApprovalResponse,
    sendMessage,
  });

  const attachmentsFromMessage = message.parts.filter(
    (part) => part.type === 'file',
  );

  const errorParts = React.useMemo(
    () =>
      message.parts
        .filter((part) => part.type === 'data-error')
        .filter((part) => !isCredentialErrorMessage(part.data)),
    [message.parts],
  );

  useDataStream();

  const partSegments = React.useMemo(
    () =>
      createMessagePartSegments(
        message.parts.filter(
          (part) =>
            part.type !== 'data-error' || isCredentialErrorMessage(part.data),
        ),
      ),
    [message.parts],
  );

  const hasOnlyErrors = React.useMemo(() => {
    const nonErrorParts = message.parts.filter(
      (part) => part.type !== 'data-error',
    );
    return errorParts.length > 0 && nonErrorParts.length === 0;
  }, [message.parts, errorParts.length]);

  const isUser = message.role === 'user';
  const messageArtifacts = artifactsByMessage?.[message.id] ?? [];

  return (
    <div
      data-testid={`message-${message.role}`}
      className="group/message w-full"
      data-role={message.role}
    >
      <div
        className={cn('flex w-full items-start gap-2 md:gap-3', {
          'justify-end': isUser,
          'justify-start': !isUser,
        })}
      >
        <div
          className={cn('flex min-w-0 flex-col gap-3', {
            'w-full': !isUser || mode === 'edit',
            'min-h-96': !isUser && requiresScrollPadding,
            'max-w-[60ch]': isUser && mode !== 'edit',
          })}
        >
          {attachmentsFromMessage.length > 0 && (
            <div
              data-testid="message-attachments"
              className={cn('flex flex-row gap-2', {
                'justify-end': isUser,
                'justify-start': !isUser,
              })}
            >
              {attachmentsFromMessage.map((attachment) => (
                <PreviewAttachment
                  key={attachment.url}
                  attachment={{
                    name: attachment.filename ?? 'file',
                    contentType: attachment.mediaType,
                    url: attachment.url,
                  }}
                />
              ))}
            </div>
          )}

          {/* Render parts with grouped tool rows */}
          <RenderedParts
            messageId={message.id}
            partSegments={partSegments}
            isLoading={isLoading}
            isUser={isUser}
            mode={mode}
            setMode={setMode}
            message={message}
            setMessages={setMessages}
            regenerate={regenerate}
            allMessages={allMessages}
            sendMessage={sendMessage}
            isMcpApprovalSubmitting={isSubmitting}
            pendingApprovalId={pendingApprovalId}
            submitApproval={submitApproval}
          />

          {/* Streaming ticker tucked under the latest assistant block */}
          {!isUser && isLoading && (
            <SparkleTicker
              state={inferTickerState(message)}
            />
          )}

          {/* Artifact thumbnail chips for any artifact this assistant message produced */}
          {!isUser && messageArtifacts.length > 0 && (
            <div className='mt-1 flex flex-wrap gap-2'>
              {messageArtifacts.map((artifact) => (
                <ArtifactThumbChip
                  key={artifact.id}
                  artifact={artifact}
                  onOpen={() => onOpenArtifact?.(artifact)}
                />
              ))}
            </div>
          )}

          {!isReadonly && !hasOnlyErrors && (
            <MessageActions
              key={`action-${message.id}`}
              message={message}
              isLoading={isLoading}
              setMode={setMode}
              errorCount={errorParts.length}
              showErrors={showErrors}
              onToggleErrors={() => setShowErrors(!showErrors)}
              initialFeedback={initialFeedback}
            />
          )}

          {errorParts.length > 0 && (hasOnlyErrors || showErrors) && (
            <div className="flex flex-col gap-2">
              {errorParts.map((part, index) => (
                <MessageError
                  key={`error-${message.id}-${index}`}
                  error={part.data}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * Walks the message's part segments and renders them — but coalesces runs
 * of `dynamic-tool` parts into a single recency-window of 3 visible rows.
 */
function RenderedParts({
  messageId,
  partSegments,
  isLoading,
  isUser,
  mode,
  setMode,
  message,
  setMessages,
  regenerate,
  allMessages,
  sendMessage,
  isMcpApprovalSubmitting,
  pendingApprovalId,
  submitApproval,
}: {
  messageId: string;
  partSegments: ReturnType<typeof createMessagePartSegments>;
  isLoading: boolean;
  isUser: boolean;
  mode: 'view' | 'edit';
  setMode: Dispatch<SetStateAction<'view' | 'edit'>>;
  message: ChatMessage;
  setMessages: UseChatHelpers<ChatMessage>['setMessages'];
  regenerate: UseChatHelpers<ChatMessage>['regenerate'];
  allMessages: ChatMessage[];
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  isMcpApprovalSubmitting: boolean;
  pendingApprovalId: string | null;
  submitApproval: (input: { approvalRequestId: string; approve: boolean }) => void;
}) {
  // Build a flat list of "items" where consecutive dynamic-tool parts get
  // grouped into a single { kind: 'tool-batch', parts: RowToolPart[] } item.
  const items: RenderItem[] = [];
  let currentBatch: RowToolPart[] | null = null;
  let mcpItems: McpToolItem[] = [];

  const flushBatch = (key: string) => {
    if (currentBatch?.length) {
      items.push({ kind: 'tool-batch', parts: currentBatch, key });
      currentBatch = null;
    }
    if (mcpItems.length) {
      for (const m of mcpItems) {
        items.push({ kind: 'mcp', mcp: m });
      }
      mcpItems = [];
    }
  };

  partSegments.forEach((parts, index) => {
    const [part] = parts;
    const key = `message-${messageId}-part-${index}`;

    // Dynamic tool: route MCP separately, otherwise stream into recency batch
    if (part.type === 'dynamic-tool') {
      const t = part as {
        type: 'dynamic-tool';
        toolCallId: string;
        toolName: string;
        state: ToolState;
        input?: unknown;
        output?: unknown;
        errorText?: string;
        callProviderMetadata?: Record<string, unknown>;
        providerExecuted?: boolean;
        approval?: { approved: boolean };
      };
      const databricks = t.callProviderMetadata?.databricks as
        | { approvalRequestId?: string; mcpServerName?: string }
        | undefined;
      const isMcpApproval = databricks?.approvalRequestId != null;

      if (isMcpApproval) {
        // MCP rows stay separate (they need explicit approval UI)
        mcpItems.push({
          key,
          serverName: databricks?.mcpServerName,
          toolName: t.toolName,
          input: t.input,
          state: t.state,
          output: t.output,
          errorText: t.errorText,
          toolCallId: t.toolCallId,
          approved: t.approval?.approved,
          providerExecuted: !!t.providerExecuted,
        });
        return;
      }

      // Plan/todo tools never render in the chat stream — they drive the
      // Progress panel in the activity rail instead. The model still calls
      // them; the rows just stay invisible to keep the chat focused on the
      // user-visible work (data fetches, infographics, file ops).
      const lowerName = t.toolName.toLowerCase().replace(/^functions\./, '');
      if (
        lowerName === 'write_todos' ||
        lowerName === 'read_todos' ||
        lowerName === 'taskcreate' ||
        lowerName === 'taskupdate'
      ) {
        return;
      }

      const effectiveState: ToolState = (() => {
        if (t.providerExecuted && !isLoading && t.state === 'input-available') {
          return 'output-available';
        }
        return t.state;
      })();

      if (currentBatch === null) currentBatch = [];
      currentBatch.push({
        toolCallId: t.toolCallId,
        toolName: t.toolName,
        state: effectiveState,
        input: t.input,
        output: t.output,
        errorText: t.errorText,
      });
      return;
    }

    // Anything that isn't a tool flushes the running batch first
    flushBatch(`${key}-batch`);

    if (part.type === 'reasoning' && part.text?.trim().length > 0) {
      items.push({
        kind: 'node',
        key,
        node: <MessageReasoning isLoading={isLoading} reasoning={part.text} />,
      });
      return;
    }

    if (part.type === 'text') {
      if (isNamePart(part)) {
        items.push({
          kind: 'node',
          key,
          node: (
            <Streamdown className="-mb-2 mt-0 border-l-4 pl-2 text-fg-3">
              {`# ${formatNamePart(part)}`}
            </Streamdown>
          ),
        });
        return;
      }
      if (mode === 'view') {
        items.push({
          kind: 'node',
          key,
          node: (
            <div
              data-testid="message-content"
              className={cn(
                'text-[13px] leading-[1.6]',
                isUser
                  ? 'ml-auto max-w-[60ch] self-end break-words rounded-[12px] border border-border-1 bg-bg-elev-1 px-4 py-2.5 text-fg-1'
                  : 'bg-transparent text-fg-1',
              )}
            >
              <Response>{sanitizeText(joinMessagePartSegments(parts))}</Response>
            </div>
          ),
        });
        return;
      }
      if (mode === 'edit') {
        items.push({
          kind: 'node',
          key,
          node: (
            <div className="flex w-full flex-row items-start gap-3">
              <div className="size-8" />
              <div className="min-w-0 flex-1">
                <MessageEditor
                  key={message.id}
                  message={message}
                  setMode={setMode}
                  setMessages={setMessages}
                  regenerate={regenerate}
                />
              </div>
            </div>
          ),
        });
        return;
      }
    }

    if (part.type === 'source-url') {
      items.push({
        kind: 'node',
        key,
        node: (
          <a
            href={part.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-baseline text-clay hover:text-clay-soft"
          >
            <sup className="text-[11px]">[{part.title || part.url}]</sup>
          </a>
        ),
      });
      return;
    }

    if (part.type === 'data-error' && isCredentialErrorMessage(part.data)) {
      items.push({
        kind: 'node',
        key,
        node: (
          <MessageOAuthError
            error={part.data}
            allMessages={allMessages}
            setMessages={setMessages}
            sendMessage={sendMessage}
          />
        ),
      });
      return;
    }
  });

  // Final flush at end
  flushBatch(`message-${messageId}-final-batch`);

  return (
    <>
      {items.map((item) => {
        if (item.kind === 'tool-batch') {
          return <ToolRowWindow key={item.key} parts={item.parts} windowSize={3} />;
        }
        if (item.kind === 'mcp') {
          const m = item.mcp;
          return (
            <McpTool key={m.toolCallId} defaultOpen={true}>
              <McpToolHeader
                serverName={m.serverName}
                toolName={m.toolName}
                state={m.state}
                approved={m.approved}
              />
              <McpToolContent>
                <McpToolInput input={m.input} />
                {m.state === 'approval-requested' && (
                  <McpApprovalActions
                    onApprove={() =>
                      submitApproval({
                        approvalRequestId: m.toolCallId,
                        approve: true,
                      })
                    }
                    onDeny={() =>
                      submitApproval({
                        approvalRequestId: m.toolCallId,
                        approve: false,
                      })
                    }
                    isSubmitting={
                      isMcpApprovalSubmitting && pendingApprovalId === m.toolCallId
                    }
                  />
                )}
                {m.state === 'output-available' && m.output != null && (
                  <ToolOutput
                    output={
                      m.errorText ? (
                        <div className="rounded border p-2 text-[var(--danger)]">
                          Error: {m.errorText}
                        </div>
                      ) : (
                        <div className="whitespace-pre-wrap font-mono text-[12.5px]">
                          {typeof m.output === 'string'
                            ? m.output
                            : JSON.stringify(m.output, null, 2)}
                        </div>
                      )
                    }
                    errorText={undefined}
                  />
                )}
              </McpToolContent>
            </McpTool>
          );
        }
        return <React.Fragment key={item.key}>{item.node}</React.Fragment>;
      })}
    </>
  );
}

type RenderItem =
  | { kind: 'node'; key: string; node: React.ReactNode }
  | { kind: 'tool-batch'; key: string; parts: RowToolPart[] }
  | { kind: 'mcp'; mcp: McpToolItem };

type McpToolItem = {
  key: string;
  serverName?: string;
  toolName: string;
  state: ToolState;
  input?: unknown;
  output?: unknown;
  errorText?: string;
  toolCallId: string;
  approved?: boolean;
  providerExecuted: boolean;
};

function inferTickerState(message: ChatMessage): import('./sparkle-ticker').TickerState {
  // Latest tool part still streaming → "Working"
  // Any reasoning text growing → "Thinking"
  // Has text already streaming → "Drafting"
  let hasText = false;
  let _hasReasoning = false;
  let hasActiveTool = false;
  for (const p of message.parts ?? []) {
    if (p.type === 'text') hasText = true;
    else if (p.type === 'reasoning') _hasReasoning = true;
    else if (p.type === 'dynamic-tool') {
      const t = p as { state: string };
      if (t.state === 'input-streaming' || t.state === 'input-available') {
        hasActiveTool = true;
      }
    }
  }
  if (hasText) return 'drafting';
  if (hasActiveTool) return 'working';
  // Default to 'thinking' (never 'starting' — we don't want a "Starting up" / "Generating response" prelude)
  return 'thinking';
}

export const PreviewMessage = memo(
  PurePreviewMessage,
  (prevProps, nextProps) => {
    if (prevProps.isLoading !== nextProps.isLoading) return false;
    if (nextProps.isLoading && prevProps.message !== nextProps.message)
      return false;
    if (prevProps.message.id !== nextProps.message.id) return false;
    if (prevProps.requiresScrollPadding !== nextProps.requiresScrollPadding)
      return false;
    if (!equal(prevProps.message.parts, nextProps.message.parts)) return false;
    if (
      prevProps.initialFeedback?.feedbackType !==
      nextProps.initialFeedback?.feedbackType
    )
      return false;
    if (
      prevProps.artifactsByMessage?.[prevProps.message.id]?.length !==
      nextProps.artifactsByMessage?.[nextProps.message.id]?.length
    )
      return false;
    return true;
  },
);

export const AwaitingResponseMessage = () => {
  return (
    <div
      data-testid="message-assistant-loading"
      className="group/message w-full"
      data-role="assistant"
    >
      <div className="flex items-start justify-start gap-3">
        <SparkleTicker state="starting" />
      </div>
    </div>
  );
};

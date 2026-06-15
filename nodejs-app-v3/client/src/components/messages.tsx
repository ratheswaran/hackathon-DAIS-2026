import { PreviewMessage } from './message';
import { memo, useEffect, useMemo } from 'react';
import equal from 'fast-deep-equal';
import type { UseChatHelpers } from '@ai-sdk/react';
import { useMessages } from '@/hooks/use-messages';
import type { ChatMessage, FeedbackMap } from '@chat-template/core';
import { useDataStream } from './data-stream-provider';
import { Conversation, ConversationContent } from './elements/conversation';
import { ArrowDownIcon } from 'lucide-react';
import type { Artifact } from '@/hooks/use-artifacts';

interface MessagesProps {
  status: UseChatHelpers<ChatMessage>['status'];
  messages: ChatMessage[];
  setMessages: UseChatHelpers<ChatMessage>['setMessages'];
  addToolApprovalResponse: UseChatHelpers<ChatMessage>['addToolApprovalResponse'];
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  regenerate: UseChatHelpers<ChatMessage>['regenerate'];
  isReadonly: boolean;
  selectedModelId: string;
  feedback?: FeedbackMap;
  artifacts?: Artifact[];
  onOpenArtifact?: (artifact: Artifact) => void;
}

function PureMessages({
  status,
  messages,
  setMessages,
  addToolApprovalResponse,
  sendMessage,
  regenerate,
  isReadonly,
  selectedModelId,
  feedback = {},
  artifacts = [],
  onOpenArtifact,
}: MessagesProps) {
  const {
    containerRef: messagesContainerRef,
    endRef: messagesEndRef,
    isAtBottom,
    scrollToBottom,
    hasSentMessage,
  } = useMessages({ status });

  useDataStream();

  useEffect(() => {
    if (status === 'submitted') {
      requestAnimationFrame(() => {
        const container = messagesContainerRef.current;
        if (container) {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: 'smooth',
          });
        }
      });
    }
  }, [status, messagesContainerRef]);

  const artifactsByMessage = useMemo(() => {
    const map: Record<string, Artifact[]> = {};
    for (const a of artifacts) {
      if (!map[a.messageId]) map[a.messageId] = [];
      map[a.messageId].push(a);
    }
    return map;
  }, [artifacts]);

  return (
    <div
      ref={messagesContainerRef}
      className="overscroll-behavior-contain -webkit-overflow-scrolling-touch flex-1 touch-pan-y overflow-y-scroll"
      style={{ overflowAnchor: 'none' }}
    >
      <Conversation className="mx-auto flex min-w-0 max-w-[720px] flex-col">
        <ConversationContent className="flex flex-col gap-5 px-4 py-6 md:gap-6">
          {messages.map((message, index) => (
            <PreviewMessage
              key={message.id}
              message={message}
              allMessages={messages}
              isLoading={status === 'streaming' && messages.length - 1 === index}
              setMessages={setMessages}
              addToolApprovalResponse={addToolApprovalResponse}
              sendMessage={sendMessage}
              regenerate={regenerate}
              isReadonly={isReadonly}
              requiresScrollPadding={hasSentMessage && index === messages.length - 1}
              initialFeedback={feedback[message.id]}
              artifactsByMessage={artifactsByMessage}
              onOpenArtifact={onOpenArtifact}
            />
          ))}

          <div
            ref={messagesEndRef}
            className="min-h-[24px] min-w-[24px] shrink-0"
          />
        </ConversationContent>
      </Conversation>

      {!isAtBottom && (
        <button
          className='-translate-x-1/2 absolute bottom-40 left-1/2 z-10 rounded-full border border-border-1 bg-bg-elev-1 p-2 text-fg-1 shadow-lg transition-colors hover:bg-bg-elev-2'
          onClick={() => scrollToBottom('smooth')}
          type="button"
          aria-label="Scroll to bottom"
        >
          <ArrowDownIcon className="size-4" />
        </button>
      )}
    </div>
  );
}

export const Messages = memo(PureMessages, (prevProps, nextProps) => {
  if (prevProps.status === 'streaming' || nextProps.status === 'streaming') {
    return false;
  }

  if (prevProps.selectedModelId !== nextProps.selectedModelId) return false;
  if (prevProps.messages.length !== nextProps.messages.length) return false;
  if (!equal(prevProps.messages, nextProps.messages)) return false;
  if (!equal(prevProps.feedback, nextProps.feedback)) return false;
  if (prevProps.artifacts !== nextProps.artifacts) return false;

  return true;
});

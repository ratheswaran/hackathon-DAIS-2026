import type { UIMessage } from 'ai';
import {
  useRef,
  useEffect,
  useState,
  useCallback,
  type Dispatch,
  type SetStateAction,
  type ChangeEvent,
  memo,
} from 'react';
import { toast } from 'sonner';
import { useLocalStorage, useWindowSize } from 'usehooks-ts';

import { PreviewAttachment } from './preview-attachment';
import { Button } from './ui/button';
import { SuggestedActions } from './suggested-actions';
import equal from 'fast-deep-equal';
import type { UseChatHelpers } from '@ai-sdk/react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowDown } from 'lucide-react';
import { useScrollToBottom } from '@/hooks/use-scroll-to-bottom';
import type { VisibilityType } from './visibility-selector';
import type { Attachment, ChatMessage } from '@chat-template/core';
import { softNavigateToChatId } from '@/lib/navigation';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { cn } from '@/lib/utils';

function PureMultimodalInput({
  chatId,
  input,
  setInput,
  status,
  stop,
  attachments,
  setAttachments,
  messages,
  setMessages,
  sendMessage,
  selectedVisibilityType,
}: {
  chatId: string;
  input: string;
  setInput: Dispatch<SetStateAction<string>>;
  status: UseChatHelpers<ChatMessage>['status'];
  stop: () => void;
  attachments: Array<Attachment>;
  setAttachments: Dispatch<SetStateAction<Array<Attachment>>>;
  messages: Array<UIMessage>;
  setMessages: UseChatHelpers<ChatMessage>['setMessages'];
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  selectedVisibilityType: VisibilityType;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { width } = useWindowSize();
  const { chatHistoryEnabled } = useAppConfig();

  const adjustHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const next = Math.min(textareaRef.current.scrollHeight, 200);
      textareaRef.current.style.height = `${Math.max(next, 24)}px`;
    }
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      adjustHeight();
    }
  }, [adjustHeight, input]);

  const resetHeight = useCallback(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '24px';
    }
  }, []);

  const [localStorageInput, setLocalStorageInput] = useLocalStorage(
    'input',
    '',
  );

  useEffect(() => {
    if (textareaRef.current) {
      const domValue = textareaRef.current.value;
      const finalValue = domValue || localStorageInput || '';
      setInput(finalValue);
      adjustHeight();
    }
  }, [localStorageInput, setInput, adjustHeight]);

  useEffect(() => {
    setLocalStorageInput(input);
  }, [input, setLocalStorageInput]);

  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
  };

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadQueue, setUploadQueue] = useState<Array<string>>([]);

  const submitForm = useCallback(() => {
    if (!input.trim() && attachments.length === 0) return;
    softNavigateToChatId(chatId, chatHistoryEnabled);

    sendMessage({
      role: 'user',
      parts: [
        ...attachments.map((attachment) => ({
          type: 'file' as const,
          url: attachment.url,
          name: attachment.name,
          mediaType: attachment.contentType,
        })),
        { type: 'text', text: input },
      ],
    });

    setAttachments([]);
    setLocalStorageInput('');
    resetHeight();
    setInput('');

    if (width && width > 768) {
      textareaRef.current?.focus();
    }
  }, [
    input,
    setInput,
    attachments,
    sendMessage,
    setAttachments,
    setLocalStorageInput,
    width,
    chatId,
    chatHistoryEnabled,
    resetHeight,
  ]);

  const uploadFile = useCallback(async (file: File) => {
    try {
      // Raw-bytes upload (no multipart): filename + real type travel as query
      // params; the body is always octet-stream so the server's JSON body
      // parser can never consume a .json upload before the route sees it.
      const qs = new URLSearchParams({
        filename: file.name,
        type: file.type || 'application/octet-stream',
      });
      const response = await fetch(`/api/files/upload?${qs}`, {
        method: 'POST',
        headers: { 'content-type': 'application/octet-stream' },
        body: file,
      });

      if (response.ok) {
        const data = await response.json();
        const { url, pathname, contentType } = data;
        return { url, name: pathname, contentType };
      }
      const { error } = await response.json();
      toast.error(error);
    } catch (_error) {
      toast.error('Failed to upload file, please try again!');
    }
  }, []);

  const handleFileChange = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files || []);
      setUploadQueue(files.map((file) => file.name));
      try {
        const uploadPromises = files.map((file) => uploadFile(file));
        const uploadedAttachments = await Promise.all(uploadPromises);
        const successful = uploadedAttachments.filter((a) => a !== undefined);
        setAttachments((current) => [...current, ...successful]);
      } catch (error) {
        console.error('Error uploading files!', error);
      } finally {
        setUploadQueue([]);
      }
    },
    [setAttachments, uploadFile],
  );

  const { isAtBottom, scrollToBottom } = useScrollToBottom();

  useEffect(() => {
    if (status === 'submitted') {
      scrollToBottom();
    }
  }, [status, scrollToBottom]);

  const isStreaming = status === 'streaming' || status === 'submitted';
  const sendDisabled =
    (!input.trim() && attachments.length === 0) || uploadQueue.length > 0;

  return (
    <div className="relative flex w-full flex-col gap-3">
      <AnimatePresence>
        {!isAtBottom && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            className="-top-12 -translate-x-1/2 absolute left-1/2 z-50"
          >
            <Button
              data-testid="scroll-to-bottom-button"
              className="rounded-full"
              size="icon"
              variant="outline"
              onClick={(event) => {
                event.preventDefault();
                scrollToBottom();
              }}
            >
              <ArrowDown />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      <input
        type="file"
        className="-top-4 -left-4 pointer-events-none fixed size-0.5 opacity-0"
        ref={fileInputRef}
        multiple
        onChange={handleFileChange}
        tabIndex={-1}
      />

      <form
        className="mx-auto flex w-full max-w-[720px] flex-col gap-2.5 rounded-[12px] border border-border-1 bg-bg-elev-1 px-4 py-3.5"
        onSubmit={(event) => {
          event.preventDefault();
          if (status !== 'ready') {
            // While streaming, queue the message rather than complaining
            if (isStreaming && input.trim()) {
              submitForm();
              return;
            }
            toast.error('Please wait for the model to finish its response!');
          } else {
            submitForm();
          }
        }}
      >
        {(attachments.length > 0 || uploadQueue.length > 0) && (
          <div
            data-testid="attachments-preview"
            className="flex flex-row items-end gap-2 overflow-x-scroll"
          >
            {attachments.map((attachment) => (
              <PreviewAttachment
                key={attachment.url}
                attachment={attachment}
                onRemove={() => {
                  setAttachments((current) =>
                    current.filter((a) => a.url !== attachment.url),
                  );
                  if (fileInputRef.current) {
                    fileInputRef.current.value = '';
                  }
                }}
              />
            ))}
            {uploadQueue.map((filename) => (
              <PreviewAttachment
                key={filename}
                attachment={{ url: '', name: filename, contentType: '' }}
                isUploading={true}
              />
            ))}
          </div>
        )}

        <textarea
          data-testid="multimodal-input"
          ref={textareaRef}
          name="message"
          placeholder="Write a message…"
          value={input}
          onChange={handleInput}
          rows={1}
          autoFocus
          className={cn(
            'm-0 block w-full resize-none border-0 bg-transparent p-0 shadow-none outline-none',
            'text-[14px] text-fg-1 leading-[1.5] placeholder:text-fg-3',
            'max-h-[200px] min-h-[24px]',
            'focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0',
            'ring-0 ring-offset-0 focus:ring-offset-0 focus-visible:ring-offset-0',
          )}
          style={{
            // Override any user-agent / shadow defaults that re-introduce a ring.
            WebkitAppearance: 'none',
            appearance: 'none',
            boxShadow: 'none',
          }}
          onKeyDown={(e) => {
            if (
              e.key === 'Enter' &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              if (status === 'ready') submitForm();
              else if (isStreaming && input.trim()) submitForm();
            }
          }}
        />

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            aria-label="Attach"
            className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-fg-2 transition-colors duration-[120ms] hover:bg-bg-elev-2 hover:text-fg-1"
          >
            <span className="text-[16px] leading-none">+</span>
          </button>

          <span className="flex-1" />

          {isStreaming && (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                stop();
                setMessages((m) => m);
              }}
              aria-label="Pause"
              data-testid="stop-button"
              className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-fg-2 transition-colors duration-[120ms] hover:bg-bg-elev-2 hover:text-fg-1"
            >
              <PauseGlyph />
            </button>
          )}

          <button
            type="submit"
            data-testid="send-button"
            disabled={sendDisabled}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-[6px] px-3.5 py-1.5 font-medium text-[12.5px]',
              'transition-[background,transform] duration-[120ms]',
              'active:scale-[0.96]',
              sendDisabled
                ? 'cursor-not-allowed bg-bg-elev-3 text-fg-3'
                : 'cursor-pointer bg-clay text-white hover:bg-clay-soft',
            )}
            style={{ transitionTimingFunction: 'var(--ease-spring)' }}
          >
            <span aria-hidden className="text-[13px] leading-none opacity-85">
              ↳
            </span>
            {isStreaming ? 'Queue' : 'Send'}
          </button>
        </div>
      </form>

      <p className="text-center text-[11px] text-fg-3">
        Always review the accuracy of responses.
      </p>

      {messages.length === 0 &&
        attachments.length === 0 &&
        uploadQueue.length === 0 && (
          <SuggestedActions
            sendMessage={sendMessage}
            chatId={chatId}
            selectedVisibilityType={selectedVisibilityType}
          />
        )}
    </div>
  );
}

function PauseGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden>
      <rect x="3" y="2" width="2" height="8" rx="0.5" fill="currentColor" />
      <rect x="7" y="2" width="2" height="8" rx="0.5" fill="currentColor" />
    </svg>
  );
}

export const MultimodalInput = memo(
  PureMultimodalInput,
  (prevProps, nextProps) => {
    if (prevProps.input !== nextProps.input) return false;
    if (prevProps.status !== nextProps.status) return false;
    if (!equal(prevProps.attachments, nextProps.attachments)) return false;
    if (prevProps.selectedVisibilityType !== nextProps.selectedVisibilityType)
      return false;
    return true;
  },
);

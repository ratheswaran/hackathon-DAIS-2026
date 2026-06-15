import { motion } from 'framer-motion';
import { memo } from 'react';
import type { UseChatHelpers } from '@ai-sdk/react';
import type { VisibilityType } from './visibility-selector';
import type { ChatMessage } from '@chat-template/core';
import { softNavigateToChatId } from '@/lib/navigation';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { Sparkle } from './sparkle-ticker';

interface SuggestedActionsProps {
  chatId: string;
  sendMessage: UseChatHelpers<ChatMessage>['sendMessage'];
  selectedVisibilityType: VisibilityType;
}

const SUGGESTED = [
  'Build a scroll-driven narrative essay on the Indian "care lottery" — how healthcare access varies up to 81× across districts.',
  'Build a 6-slide deck on medical deserts in India — cover, the care lottery, zero-facility districts, the Bihar–Kerala burden gap, a chart slide, and a closing.',
  'Do a deep-dive analysis of the worst medical-desert districts — high health burden, fewest nearby facilities — and save it as a Databricks notebook.',
];

function PureSuggestedActions({ chatId, sendMessage }: SuggestedActionsProps) {
  const { chatHistoryEnabled } = useAppConfig();

  return (
    <div
      data-testid="suggested-actions"
      className="mx-auto mt-4 flex w-full max-w-[720px] flex-col"
    >
      {SUGGESTED.map((suggestion, index) => (
        <motion.button
          key={suggestion}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ delay: 0.05 * index, ease: [0.16, 1, 0.3, 1] }}
          type="button"
          className="group flex w-full cursor-pointer items-center gap-2.5 border-border-1 border-b py-2.5 text-left text-[14px] text-fg-2 transition-colors duration-[120ms] last:border-b-0 hover:text-fg-1"
          onClick={() => {
            softNavigateToChatId(chatId, chatHistoryEnabled);
            sendMessage({
              role: 'user',
              parts: [{ type: 'text', text: suggestion }],
            });
          }}
        >
          <Sparkle size={20} />
          {suggestion}
        </motion.button>
      ))}
    </div>
  );
}

export const SuggestedActions = memo(
  PureSuggestedActions,
  (prevProps, nextProps) => {
    if (prevProps.chatId !== nextProps.chatId) return false;
    if (prevProps.selectedVisibilityType !== nextProps.selectedVisibilityType)
      return false;
    return true;
  },
);

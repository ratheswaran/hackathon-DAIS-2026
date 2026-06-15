import { cn } from '@/lib/utils';
import { LottieSparkle } from './lottie-sparkle';

export type TickerState =
  | 'starting'
  | 'thinking'
  | 'working'
  | 'drafting'
  | 'done'
  | 'idle';

const LABELS: Record<TickerState, string> = {
  starting: 'Starting up',
  thinking: 'Thinking',
  working: 'Working',
  drafting: 'Drafting answer',
  done: 'Done',
  idle: 'Idle',
};

/**
 * Brand glyph — the animated Lottie cube cluster. Sizes either via an explicit
 * `size` (px) or with font-size via em on the className.
 */
export function Sparkle({
  className,
  size,
}: {
  className?: string;
  size?: number;
}) {
  return <LottieSparkle className={cn('leading-none', className)} size={size} />;
}

export function SparkleTicker({
  state = 'working',
  label,
  className,
}: {
  state?: TickerState;
  label?: string;
  className?: string;
}) {
  const text = label ?? LABELS[state];
  // Shimmer while the agent is actively doing something; settled states stay plain.
  const live = state !== 'done' && state !== 'idle';
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex items-center gap-2.5 py-1.5 text-[14px] text-fg-1',
        className,
      )}
    >
      <LottieSparkle variant="thinking" className="text-[18px]" />
      <span className={cn(live && 'shimmer-text')}>{text}</span>
    </div>
  );
}

import { cn } from '@/lib/utils';

export type Decision = {
  question: string;
  answer: string;
};

export function DecisionsCard({
  decisions,
  className,
}: {
  decisions: Decision[];
  className?: string;
}) {
  if (!decisions.length) return null;

  return (
    <div
      className={cn(
        'rounded-[12px] border border-border-1 bg-bg-elev-1 px-[22px] py-[18px]',
        className,
      )}
      role="region"
      aria-label="Decisions"
    >
      {decisions.map((decision, i) => (
        <div key={i} className="py-[5px] text-[14px] leading-snug">
          <span className="block font-medium text-fg-1">{decision.question}</span>
          <span className="block text-fg-2">{decision.answer}</span>
        </div>
      ))}
    </div>
  );
}

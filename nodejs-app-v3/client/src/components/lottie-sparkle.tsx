import { cn } from '@/lib/utils';
import { useEffect, useRef } from 'react';
import type { AnimationItem, LottiePlayer } from 'lottie-web';

/**
 * Animated brand glyphs (Lottie), replacing the static 4-point sparkle.
 *
 * Two variants (swapped per user call 2026-06-11 evening):
 *  - `glyph` (default) — the isometric cube-cluster in its NATIVE colors
 *    (white cube faces + dark outlines — it reads as a white mark on the dark
 *    UI). Used for the greeting, suggestion rows and the Genie tool-row icon.
 *  - `thinking` — the hand-drawn comet/dot morph, recolored WHITE via CSS
 *    `currentColor` overrides. Used wherever the agent is working: the status
 *    ticker and streaming indicators. Its source loop ends on ~15 near-empty
 *    frames, so we loop the visible segment only — it never blinks out.
 *
 * Assets are fetched once per variant from /sparkle-*.json and shared across
 * instances; reduced-motion pins a fully-drawn frame instead of animating.
 */

type Variant = 'glyph' | 'thinking';

const SOURCES: Record<
  Variant,
  {
    src: string;
    segment: [number, number] | null;
    restFrame: number;
    /** recolor everything to currentColor (vs keep the baked colors) */
    recolor: boolean;
    /**
     * Optional crop. The artwork sits centered in a 256×256 canvas but only
     * fills a small region (measured content bbox of the cube cluster: x86 y80
     * w83 h96), so the rendered mark looked tiny next to text. We tighten the
     * SVG viewBox to the drawn content (+~9px pad) via lottie-web's
     * `rendererSettings.viewBoxSize` so the glyph fills its box.
     */
    viewBox: string | null;
  }
> = {
  glyph: {
    src: '/sparkle-glyph.json',
    segment: null,
    restFrame: 45,
    recolor: false,
    viewBox: '77 71 101 114',
  },
  thinking: {
    src: '/sparkle-thinking.json',
    segment: [2, 52],
    restFrame: 6,
    recolor: true,
    viewBox: null,
  },
};

let lottieMod: Promise<
  typeof import('lottie-web/build/player/lottie_light')
> | null = null;
const dataCache: Partial<Record<Variant, Promise<unknown>>> = {};

function loadLottie() {
  if (!lottieMod) {
    lottieMod = import('lottie-web/build/player/lottie_light');
  }
  return lottieMod;
}
function loadData(variant: Variant) {
  if (!dataCache[variant]) {
    dataCache[variant] = fetch(SOURCES[variant].src).then((r) => r.json());
  }
  return dataCache[variant] as Promise<unknown>;
}

export function LottieSparkle({
  className,
  size,
  variant = 'glyph',
}: {
  className?: string;
  /** Optional pixel size; defaults to 1.15em via the .lottie-spark class */
  size?: number;
  variant?: Variant;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let anim: AnimationItem | undefined;
    let alive = true;
    Promise.all([loadLottie(), loadData(variant)]).then(([mod, data]) => {
      const el = ref.current;
      if (!alive || !el) return;
      const modAny = mod as { default?: LottiePlayer };
      const lottie = modAny.default ?? (mod as unknown as LottiePlayer);
      const cfg = SOURCES[variant];
      const reduced = window.matchMedia(
        '(prefers-reduced-motion: reduce)',
      ).matches;
      anim = lottie.loadAnimation({
        container: el,
        renderer: 'svg',
        loop: true,
        autoplay: false,
        animationData: data,
        // Crop the generated <svg> viewBox to the drawn artwork so the mark
        // fills its box (the source canvas is mostly empty padding).
        ...(cfg.viewBox
          ? { rendererSettings: { viewBoxSize: cfg.viewBox } }
          : {}),
      });
      if (reduced) {
        anim.goToAndStop(cfg.restFrame, true);
      } else if (cfg.segment) {
        anim.playSegments(cfg.segment, true);
      } else {
        anim.play();
      }
    });
    return () => {
      alive = false;
      anim?.destroy();
    };
  }, [variant]);

  return (
    <span
      aria-hidden
      ref={ref}
      className={cn(
        'lottie-spark',
        !SOURCES[variant].recolor && 'lottie-spark--native',
        className,
      )}
      style={size ? { width: size, height: size } : undefined}
    />
  );
}

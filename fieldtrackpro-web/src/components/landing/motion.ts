import { useEffect, useState, type RefObject } from 'react';

const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

function getReduced(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(REDUCED_QUERY).matches
    : false;
}

/** Live `prefers-reduced-motion` value. Motion code checks this before animating anything. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(getReduced);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(REDUCED_QUERY);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

/**
 * Adds `is-in` to every `[data-reveal]` element under `root` once it scrolls into view.
 * Without IntersectionObserver (or with reduced motion) everything is shown at once.
 */
export function useReveal(root: RefObject<HTMLElement>, reduced: boolean): void {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const items = Array.from(el.querySelectorAll<HTMLElement>('[data-reveal]'));
    if (reduced || typeof IntersectionObserver === 'undefined') {
      items.forEach((i) => i.classList.add('is-in'));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-in');
            io.unobserve(e.target);
          }
        }
      },
      { rootMargin: '0px 0px -10% 0px', threshold: 0.12 },
    );
    items.forEach((i) => io.observe(i));
    return () => io.disconnect();
  }, [root, reduced]);
}

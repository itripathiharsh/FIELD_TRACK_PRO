import { useEffect, useRef, useState, type MutableRefObject, type RefObject } from 'react';

const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

/**
 * `?motion=on` forces full motion and `?motion=off` forces the reduced experience.
 * QA-only override so both paths can be checked on any machine; default follows the OS.
 */
function motionOverride(): boolean | null {
  if (typeof window === 'undefined') return null;
  const v = new URLSearchParams(window.location.search).get('motion');
  return v === 'on' ? false : v === 'off' ? true : null;
}

function getReduced(): boolean {
  const o = motionOverride();
  if (o !== null) return o;
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(REDUCED_QUERY).matches
    : false;
}

/** Live `prefers-reduced-motion` value. Motion code checks this before animating anything. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(getReduced);
  useEffect(() => {
    if (motionOverride() !== null || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(REDUCED_QUERY);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

/** True below the given width (live). */
export function useIsNarrow(maxWidth = 767): boolean {
  const q = `(max-width: ${maxWidth}px)`;
  const get = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(q).matches;
  const [narrow, setNarrow] = useState(get);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(q);
    const onChange = () => setNarrow(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, [q]);
  return narrow;
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
      { rootMargin: '0px 0px -8% 0px', threshold: 0.15 },
    );
    items.forEach((i) => io.observe(i));
    return () => io.disconnect();
  }, [root, reduced]);
}

/** True while the element is (near) the viewport. Defaults to true without IntersectionObserver. */
export function useInView(target: RefObject<HTMLElement>, rootMargin = '0px'): boolean {
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = target.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { rootMargin });
    io.observe(el);
    return () => io.disconnect();
  }, [target, rootMargin]);
  return inView;
}

/**
 * Scroll progress (0..1) of a tall `target` through the viewport, kept in a ref (read per
 * frame by the 3D scene, no re-render) and mirrored to the `--p` CSS variable.
 * `onStep` fires when the bucket index (of `steps`) changes.
 */
export function useScrollProgress(
  target: RefObject<HTMLElement>,
  steps = 1,
  onStep?: (i: number) => void,
): MutableRefObject<number> {
  const progress = useRef(0);
  const last = useRef(-1);
  const stepRef = useRef(onStep);
  stepRef.current = onStep;
  useEffect(() => {
    const el = target.current;
    if (!el) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = el.getBoundingClientRect();
      const total = rect.height - window.innerHeight;
      const p = total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0;
      progress.current = p;
      el.style.setProperty('--p', p.toFixed(4));
      const idx = Math.min(steps - 1, Math.floor(p * steps));
      if (idx !== last.current) {
        last.current = idx;
        stepRef.current?.(idx);
      }
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [target, steps]);
  return progress;
}

/** Lenis smooth scrolling (desktop pointer devices, motion allowed). Loaded on demand. */
export function useSmoothScroll(enabled: boolean): void {
  useEffect(() => {
    if (!enabled || typeof window.matchMedia !== 'function' || !window.matchMedia('(pointer: fine)').matches) return;
    let destroyed = false;
    let raf = 0;
    let lenis: { raf: (t: number) => void; destroy: () => void } | null = null;
    import('lenis')
      .then(({ default: Lenis }) => {
        if (destroyed) return;
        const l = new Lenis({ lerp: 0.11, anchors: { offset: -72 } });
        lenis = l;
        const loop = (t: number) => {
          l.raf(t);
          raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
      })
      .catch(() => undefined);
    return () => {
      destroyed = true;
      cancelAnimationFrame(raf);
      lenis?.destroy();
    };
  }, [enabled]);
}

/** Can this browser create a WebGL context? */
export function canUseWebGL(): boolean {
  if (typeof window === 'undefined' || typeof window.WebGLRenderingContext === 'undefined') return false;
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

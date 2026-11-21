import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, Download } from 'lucide-react';
import { APK_DOWNLOAD_FILENAME, APK_DOWNLOAD_URL, formatApkMeta, type ApkMeta } from '../../config/apk';
import { canUseWebGL, useInView, useIsNarrow, useScrollProgress } from './motion';
import { CELL, MAP_DESKTOP, PINS_DESKTOP, ROUTES_DESKTOP, districts } from './scene/data';

const TerritoryScene = lazy(() => import('./scene/TerritoryScene'));

/** Static top-down render of the same demo map: the LCP-safe poster and the no-WebGL fallback. */
export const MapPoster: React.FC = () => {
  const list = useMemo(() => districts(MAP_DESKTOP), []);
  const s = 40;
  const W = MAP_DESKTOP.cols * CELL * s;
  const H = MAP_DESKTOP.rows * CELL * s;
  const tx = (x: number) => x * s + W / 2;
  const tz = (z: number) => z * s + H / 2;
  const size = (CELL - 0.34) * s;
  return (
    <svg className="ftl-poster" viewBox={`0 0 ${W} ${H}`} aria-hidden="true" preserveAspectRatio="xMidYMid slice">
      <rect width={W} height={H} fill="#0d0d10" />
      {list.map((d, i) => (
        <rect
          key={i}
          x={tx(d.x) - size / 2}
          y={tz(d.z) - size / 2}
          width={size}
          height={size}
          rx={3}
          fill={d.zone ? '#2a2119' : '#18181c'}
          stroke="rgba(255,255,255,.04)"
        />
      ))}
      {ROUTES_DESKTOP.map((r, i) => (
        <polyline
          key={i}
          points={r.map(([x, z]) => `${tx(x)},${tz(z)}`).join(' ')}
          fill="none"
          stroke={i === 0 ? '#ff9f2e' : 'rgba(237,237,237,.4)'}
          strokeWidth={i === 0 ? 4 : 2.5}
          strokeLinejoin="round"
        />
      ))}
      {PINS_DESKTOP.map(([ri, vi], i) => {
        const [x, z] = ROUTES_DESKTOP[ri][vi];
        return <circle key={i} cx={tx(x)} cy={tz(z)} r={6} fill={ri === 0 ? '#ff9f2e' : '#ededed'} />;
      })}
    </svg>
  );
};

const LINE_1 = ['Every', 'visit', 'verified.'];
const LINE_2 = ['Every', 'rupee', 'reconciled.'];

const Kinetic: React.FC<{ words: string[]; start: number; className?: string }> = ({ words, start, className }) => (
  <span className={`ftl-line ${className ?? ''}`}>
    {words.map((w, i) => (
      <span key={i} className="ftl-word">
        <span style={{ '--i': start + i } as React.CSSProperties}>{w}</span>
      </span>
    ))}
  </span>
);

const inr = (n: number) => `₹${n.toLocaleString('en-IN')}`;

/** Demo counters that tick while motion is allowed. */
function useDemoTicker(enabled: boolean) {
  const [s, setS] = useState({ visits: 86, verified: 83, collected: 982_400 });
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => {
      setS((v) => {
        const visit = Math.random() < 0.45;
        return {
          visits: v.visits + (visit ? 1 : 0),
          verified: v.verified + (visit && Math.random() < 0.94 ? 1 : 0),
          collected: v.collected + Math.round((200 + Math.random() * 2600) / 50) * 50,
        };
      });
    }, 1400);
    return () => window.clearInterval(id);
  }, [enabled]);
  return s;
}

export const Hero: React.FC<{ reduced: boolean; meta: ApkMeta | null }> = ({ reduced, meta }) => {
  const sectionRef = useRef<HTMLElement>(null);
  const mobile = useIsNarrow(767);
  const progress = useScrollProgress(sectionRef);
  const inView = useInView(sectionRef, '200px');
  const [load3d, setLoad3d] = useState(false);
  const [ready, setReady] = useState(false);
  const stats = useDemoTicker(!reduced && inView);

  // The 3D scene loads after first paint (idle), and only when WebGL works.
  useEffect(() => {
    if (!canUseWebGL()) return;
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      cancelIdleCallback?: (n: number) => void;
    };
    const go = () => setLoad3d(true);
    if (typeof w.requestIdleCallback === 'function') {
      const id = w.requestIdleCallback(go, { timeout: 1200 });
      return () => w.cancelIdleCallback?.(id);
    }
    const id = window.setTimeout(go, 300);
    return () => window.clearTimeout(id);
  }, []);

  const apk = formatApkMeta(meta);

  return (
    <section
      id="top"
      ref={sectionRef}
      className={`ftl-hero${reduced ? ' is-static' : ''}${ready ? ' is-3d' : ''}`}
      aria-labelledby="ftl-hero-title"
    >
      <div className="ftl-hero-pin">
        <div className="ftl-hero-stage" aria-hidden="true">
          <div className="ftl-poster-wrap">
            <MapPoster />
          </div>
          {load3d && (
            <Suspense fallback={null}>
              <TerritoryScene progress={progress} reduced={reduced} mobile={mobile} active={inView} onReady={() => setReady(true)} />
            </Suspense>
          )}
          <div className="ftl-hero-vignette" />
        </div>

        <div className="ftl-wrap ftl-hero-ui">
          <div className="ftl-hero-copy">
            <p className="ftl-eyebrow">
              <span className="ftl-live" /> Field operations, live
            </p>
            <h1 id="ftl-hero-title" className="ftl-display">
              <Kinetic words={LINE_1} start={0} />
              <Kinetic words={LINE_2} start={3} className="ftl-line--dim" />
            </h1>
            <p className="ftl-hero-lead">
              FieldTrack Pro puts your reps, outlets and collections on one live map: GPS-verified check-ins on Android,
              a command center on the web, reconciled with Tally Prime.
            </p>
            <div className="ftl-hero-ctas">
              <Link to="/login" className="ftl-btn ftl-btn--solid" data-testid="landing-use-web">
                Use on web <ArrowRight aria-hidden="true" />
              </Link>
              <a href={APK_DOWNLOAD_URL} download={APK_DOWNLOAD_FILENAME} className="ftl-btn ftl-btn--line" data-testid="landing-download-apk">
                <Download aria-hidden="true" />
                <span>
                  Download app
                  <small>Android{apk ? ` · ${apk}` : ''}</small>
                </span>
              </a>
            </div>
          </div>

          <dl className="ftl-hud" aria-label="Live demo figures">
            <div>
              <dt>Visits today</dt>
              <dd>{stats.visits}</dd>
            </div>
            <div>
              <dt>Geo-verified</dt>
              <dd>{Math.round((stats.verified / stats.visits) * 100)}%</dd>
            </div>
            <div>
              <dt>Collected</dt>
              <dd>{inr(stats.collected)}</dd>
            </div>
            <p className="ftl-hud-note">Demo data</p>
          </dl>

          <div className="ftl-hero-caption" aria-hidden="true">
            <span className="ftl-mono">02 · Command center</span>
            <p>
              The web dashboard and the rep’s phone, fed by the same live map. <ArrowUpRight />
            </p>
          </div>

          <div className="ftl-scroll-cue" aria-hidden="true">
            <span />
            Scroll
          </div>
        </div>
      </div>
    </section>
  );
};

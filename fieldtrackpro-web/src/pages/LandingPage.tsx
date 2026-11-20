import React, { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  CalendarDays,
  ClipboardList,
  Download,
  IndianRupee,
  MapPin,
  Monitor,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  WifiOff,
} from 'lucide-react';
import { APK_DOWNLOAD_FILENAME, APK_DOWNLOAD_URL, APK_META_PATH, formatApkMeta } from '../config/apk';
import { PhoneScreen, type PhoneView } from '../components/landing/Mockups';
import { usePrefersReducedMotion, useReveal, useScrollProgress } from '../components/landing/motion';
import '../components/landing/landing.css';

// The 3D hero scene is its own chunk; the static hero copy and CTAs paint first.
const DeviceScene = lazy(() => import('../components/landing/DeviceScene'));

interface ApkMetaFull {
  versionName?: string;
  versionCode?: number;
  sizeBytes?: number;
  sha256?: string;
}

const FEATURES = [
  {
    icon: MapPin,
    title: 'GPS-verified visits',
    body: 'Check-ins are accepted only inside the outlet’s geofence, with accuracy and time stamped on every visit.',
  },
  {
    icon: CalendarDays,
    title: 'Monthly visit planning',
    body: 'Plan routes per territory and rep, then track planned versus actual visits day by day.',
  },
  {
    icon: IndianRupee,
    title: 'Collections & payments',
    body: 'Capture cash, cheque and UPI payments with proof photos, reviewed by admins before they post.',
  },
  {
    icon: RefreshCw,
    title: 'Tally reconciliation',
    body: 'Invoices, vouchers and receipts stay in step with Tally, with ageing reports built from the ledger.',
  },
  {
    icon: WifiOff,
    title: 'Works offline',
    body: 'Reps keep working without signal; visits, photos and payments queue up and sync when they reconnect.',
  },
  {
    icon: ClipboardList,
    title: 'Forms & requirements',
    body: 'Custom forms and customer requirements captured on the visit, routed straight to the back office.',
  },
  {
    icon: BarChart3,
    title: 'Reports that answer',
    body: 'Daily logs, collections workbench and outlet coverage reports for admins and accountants.',
  },
  {
    icon: ShieldCheck,
    title: 'Role-based access',
    body: 'Admins see every territory; employees see only their own customers, visits and submissions.',
  },
];

const STEPS: { view: PhoneView; title: string; body: string }[] = [
  { view: 'route', title: 'Plan the day', body: 'Each rep opens the app to today’s route, built from the monthly visit plan.' },
  { view: 'checkin', title: 'Check in on site', body: 'The phone confirms the rep is inside the outlet’s geofence before the visit starts.' },
  { view: 'capture', title: 'Capture the visit', body: 'Orders, payments, photos and customer requirements are recorded in one flow.' },
  { view: 'sync', title: 'Sync & reconcile', body: 'Everything lands on the admin dashboard and is matched against Tally.' },
];

const MARQUEE = [
  'Geofenced check-ins',
  'Offline queue',
  'Tally sync',
  'Photo proof',
  'UPI & cheque capture',
  'Visit planning',
  'Live field map',
  'Ageing reports',
  'Custom forms',
  'Role-based access',
];

function formatSize(bytes?: number): string | null {
  return bytes && bytes > 0 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : null;
}

function useApkMeta(): ApkMetaFull | null {
  const [meta, setMeta] = useState<ApkMetaFull | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(APK_META_PATH, { cache: 'no-store' })
      .then((r) => (r.ok && (r.headers.get('content-type') ?? '').includes('json') ? r.json() : null))
      .then((m) => {
        if (!cancelled && m) setMeta(m as ApkMetaFull);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return meta;
}

const Logo: React.FC = () => (
  <span className="ftl-brand">
    <span className="ftl-brand-mark" aria-hidden="true">
      <MapPin />
    </span>
    FieldTrack <em>Pro</em>
  </span>
);

const DownloadButton: React.FC<{ meta: ApkMetaFull | null; variant?: 'primary' | 'ghost'; id?: string }> = ({
  meta,
  variant = 'ghost',
  id,
}) => (
  <a
    id={id}
    href={APK_DOWNLOAD_URL}
    download={APK_DOWNLOAD_FILENAME}
    className={`ftl-btn ftl-btn--${variant}`}
    data-testid="landing-download-apk"
  >
    <Download aria-hidden="true" />
    <span>
      Download app
      {formatApkMeta(meta) && <small>Android · {formatApkMeta(meta)}</small>}
    </span>
  </a>
);

/** Feature card with a pointer-following tilt and spotlight (pointer devices, motion allowed). */
const FeatureCard: React.FC<{ feature: (typeof FEATURES)[number]; reduced: boolean; index: number }> = ({
  feature: { icon: Icon, title, body },
  reduced,
  index,
}) => {
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (reduced || e.pointerType !== 'mouse') return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width;
    const y = (e.clientY - r.top) / r.height;
    e.currentTarget.style.setProperty('--mx', `${x * 100}%`);
    e.currentTarget.style.setProperty('--my', `${y * 100}%`);
    e.currentTarget.style.setProperty('--tx', `${(0.5 - y) * 10}deg`);
    e.currentTarget.style.setProperty('--ty', `${(x - 0.5) * 12}deg`);
  };
  const onLeave = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.style.setProperty('--tx', '0deg');
    e.currentTarget.style.setProperty('--ty', '0deg');
  };
  return (
    <div
      className="ftl-card"
      data-reveal
      style={{ '--d': `${(index % 4) * 70}ms` } as React.CSSProperties}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
    >
      <div className="ftl-card-icon">
        <Icon aria-hidden="true" />
      </div>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
};

export const LandingPage: React.FC = () => {
  const reduced = usePrefersReducedMotion();
  const rootRef = useRef<HTMLDivElement>(null);
  const storyRef = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  const meta = useApkMeta();
  const [scrolled, setScrolled] = useState(false);

  useReveal(rootRef, reduced);
  useScrollProgress(storyRef, STEPS.length, useCallback((i: number) => setStep(i), []));

  useEffect(() => {
    const prevTitle = document.title;
    document.title = 'FieldTrack Pro — Field force management for sales teams';
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      document.title = prevTitle;
      window.removeEventListener('scroll', onScroll);
    };
  }, []);

  return (
    <div ref={rootRef} className={`ftl${reduced ? ' ftl--still' : ''}`}>
      <a href="#main" className="ftl-skip">
        Skip to content
      </a>

      <header className={`ftl-nav${scrolled ? ' is-scrolled' : ''}`}>
        <div className="ftl-wrap ftl-nav-inner">
          <Link to="/" aria-label="FieldTrack Pro home">
            <Logo />
          </Link>
          <nav aria-label="Sections" className="ftl-nav-links">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <a href="#get">Get the app</a>
          </nav>
          <Link to="/login" className="ftl-btn ftl-btn--small">
            Sign in
          </Link>
        </div>
      </header>

      <main id="main">
        {/* Hero */}
        <section className="ftl-hero" aria-labelledby="ftl-hero-title">
          <div className="ftl-floor-grid" aria-hidden="true" />
          <div className="ftl-orb ftl-orb--a" aria-hidden="true" />
          <div className="ftl-orb ftl-orb--b" aria-hidden="true" />
          <div className="ftl-wrap ftl-hero-grid">
            <div className="ftl-hero-copy">
              <p className="ftl-eyebrow ftl-in" style={{ '--d': '0ms' } as React.CSSProperties}>
                <span className="ftl-live-dot" /> Field force management
              </p>
              <h1 id="ftl-hero-title" className="ftl-in" style={{ '--d': '80ms' } as React.CSSProperties}>
                Every visit verified.
                <br />
                <span className="ftl-grad">Every rupee accounted for.</span>
              </h1>
              <p className="ftl-lead ftl-in" style={{ '--d': '160ms' } as React.CSSProperties}>
                FieldTrack Pro connects your sales reps in the field with the back office: GPS-verified
                check-ins, orders and collections on Android, and a live admin dashboard reconciled with Tally.
              </p>
              <div className="ftl-ctas ftl-in" style={{ '--d': '240ms' } as React.CSSProperties}>
                <Link to="/login" className="ftl-btn ftl-btn--primary" data-testid="landing-use-web">
                  <Monitor aria-hidden="true" />
                  <span>Use on web</span>
                  <ArrowRight aria-hidden="true" className="ftl-btn-arrow" />
                </Link>
                <DownloadButton meta={meta} />
              </div>
              <p className="ftl-hint ftl-in" style={{ '--d': '320ms' } as React.CSSProperties}>
                Web for admins and accountants · Android app for field reps
              </p>
            </div>
            <div className="ftl-hero-visual">
              <Suspense fallback={<div className="ftl-scene ftl-scene--placeholder" aria-hidden="true" />}>
                <DeviceScene reduced={reduced} />
              </Suspense>
            </div>
          </div>
        </section>

        {/* Capability marquee */}
        <div className="ftl-marquee" aria-label="Capabilities">
          <div className="ftl-marquee-track">
            {[...MARQUEE, ...MARQUEE].map((m, i) => (
              <span key={i} aria-hidden={i >= MARQUEE.length ? true : undefined}>
                {m}
              </span>
            ))}
          </div>
        </div>

        {/* Features */}
        <section id="features" className="ftl-section" aria-labelledby="ftl-features-title">
          <div className="ftl-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-eyebrow">What it does</p>
              <h2 id="ftl-features-title">One system from the shop floor to the ledger</h2>
              <p className="ftl-sub">
                Built for distribution teams that run hundreds of outlet visits a day and need the numbers to add up.
              </p>
            </div>
            <div className="ftl-cards">
              {FEATURES.map((f, i) => (
                <FeatureCard key={f.title} feature={f} reduced={reduced} index={i} />
              ))}
            </div>
          </div>
        </section>

        {/* Scroll story */}
        <section id="how" ref={storyRef} className="ftl-story" aria-labelledby="ftl-how-title">
          <div className="ftl-story-sticky">
            <div className="ftl-wrap ftl-story-grid">
              <div>
                <div className="ftl-head ftl-head--left" data-reveal>
                  <p className="ftl-eyebrow">How it works</p>
                  <h2 id="ftl-how-title">A rep’s day, start to sync</h2>
                </div>
                <ol className="ftl-steps">
                  {STEPS.map((s, i) => (
                    <li key={s.title} className={i === step ? 'is-active' : i < step ? 'is-done' : ''}>
                      <span className="ftl-step-num">{i + 1}</span>
                      <div>
                        <h3>{s.title}</h3>
                        <p>{s.body}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                <div className="ftl-story-bar" aria-hidden="true">
                  <span />
                </div>
              </div>
              <div className="ftl-story-phone" aria-hidden="true">
                <div className="ftl-phone ftl-phone--flat">
                  <div className="ftl-phone-body">
                    <PhoneScreen view={STEPS[step].view} />
                    <span className="ftl-glare" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Get the app */}
        <section id="get" className="ftl-section" aria-labelledby="ftl-get-title">
          <div className="ftl-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-eyebrow">Get started</p>
              <h2 id="ftl-get-title">Pick your screen</h2>
            </div>
            <div className="ftl-get">
              <div className="ftl-get-card" data-reveal>
                <div className="ftl-get-icon">
                  <Monitor aria-hidden="true" />
                </div>
                <h3>Use on web</h3>
                <p>
                  The admin dashboard for managers and accountants: territories, employees, visit plans, collections and
                  reports. Works in any modern browser.
                </p>
                <Link to="/login" className="ftl-btn ftl-btn--primary">
                  <span>Sign in on the web</span>
                  <ArrowRight aria-hidden="true" className="ftl-btn-arrow" />
                </Link>
              </div>
              <div className="ftl-get-card" data-reveal style={{ '--d': '90ms' } as React.CSSProperties}>
                <div className="ftl-get-icon ftl-get-icon--alt">
                  <Smartphone aria-hidden="true" />
                </div>
                <h3>Android app</h3>
                <p>
                  For field reps: today’s route, geofenced check-ins, orders, payments and photos, even offline.
                  Android 8.0 or later.
                </p>
                <DownloadButton meta={meta} variant="primary" id="download" />
                <dl className="ftl-apk-meta">
                  {meta?.versionName && (
                    <div>
                      <dt>Version</dt>
                      <dd>
                        {meta.versionName}
                        {meta.versionCode ? ` (${meta.versionCode})` : ''}
                      </dd>
                    </div>
                  )}
                  {formatSize(meta?.sizeBytes) && (
                    <div>
                      <dt>Size</dt>
                      <dd>{formatSize(meta?.sizeBytes)}</dd>
                    </div>
                  )}
                  {meta?.sha256 && (
                    <div className="ftl-apk-sha">
                      <dt>SHA-256</dt>
                      <dd>
                        <code>{meta.sha256}</code>
                      </dd>
                    </div>
                  )}
                </dl>
                <p className="ftl-fine">
                  The APK is installed directly, not from Google Play: when Android asks, allow your browser to install
                  apps from this source.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="ftl-footer">
        <div className="ftl-wrap ftl-footer-inner">
          <Logo />
          <span>© {new Date().getFullYear()} FieldTrack Pro</span>
          <Link to="/login">Sign in</Link>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;

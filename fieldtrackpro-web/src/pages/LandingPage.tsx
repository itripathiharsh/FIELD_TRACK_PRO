import React, { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  Building2,
  CalendarDays,
  Check,
  ChevronDown,
  ClipboardList,
  Download,
  Fingerprint,
  IndianRupee,
  KeyRound,
  Layers,
  Lock,
  MapPin,
  Menu,
  Monitor,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  Smartphone,
  Users,
  WifiOff,
  X,
  Zap,
} from 'lucide-react';
import { APK_DOWNLOAD_FILENAME, APK_DOWNLOAD_URL, APK_META_PATH, formatApkMeta } from '../config/apk';
import { usePrefersReducedMotion, useReveal } from '../components/landing/motion';
import '../components/landing/landing.css';

// The 3D hero scene is its own chunk; the hero copy and CTAs paint first.
const DeviceScene = lazy(() => import('../components/landing/DeviceScene'));

interface ApkMetaFull {
  versionName?: string;
  versionCode?: number;
  sizeBytes?: number;
  sha256?: string;
}

const NAV_LINKS = [
  { id: 'home', label: 'Home' },
  { id: 'features', label: 'Features' },
  { id: 'solutions', label: 'Solutions' },
  { id: 'how', label: 'How It Works' },
  { id: 'security', label: 'Security' },
  { id: 'faq', label: 'FAQ' },
];

const STRIP = [
  { icon: Zap, title: 'Field Team Management', body: 'Plan, assign and track field activities.' },
  { icon: Layers, title: 'Outlet & Territory Control', body: 'Manage outlets, zones and coverage.' },
  { icon: BarChart3, title: 'Collections & Outstanding', body: 'Track payments and overdue in real time.' },
  { icon: ShieldCheck, title: 'Tally Integration', body: 'Sync financial data with Tally Prime.' },
];

const FEATURES = [
  { icon: MapPin, title: 'GPS-verified visits', body: 'Check-ins are accepted only inside the outlet’s geofence, with accuracy and time stamped on every visit.' },
  { icon: CalendarDays, title: 'Monthly visit planning', body: 'Plan routes per territory and rep, then track planned versus actual visits day by day.' },
  { icon: IndianRupee, title: 'Collections & payments', body: 'Capture cash, cheque and UPI payments with proof photos, reviewed by admins before they post.' },
  { icon: RefreshCw, title: 'Tally reconciliation', body: 'Invoices, vouchers and receipts stay in step with Tally Prime, with ageing built from the ledger.' },
  { icon: WifiOff, title: 'Works offline', body: 'Reps keep working without signal; visits, photos and payments queue and sync when they reconnect.' },
  { icon: ClipboardList, title: 'Forms & requirements', body: 'Custom forms and customer requirements captured on the visit and routed to the back office.' },
  { icon: BarChart3, title: 'Executive BI dashboard', body: 'Filter by brand, zone, area, field officer and overdue ageing to see the whole business at once.' },
  { icon: Users, title: 'Team & daily logs', body: 'Employee profiles, daily activity logs and ad-hoc visit review for every field officer.' },
];

const SOLUTIONS = [
  {
    icon: Building2,
    title: 'Owners & admins',
    body: 'One command center for every brand, zone and rep.',
    points: ['Multi-brand BI with drill-down filters', 'Territory, area and outlet master data', 'Monthly close and lock workflow'],
  },
  {
    icon: IndianRupee,
    title: 'Accountants',
    body: 'Collections and outstanding you can trust.',
    points: ['Read-only access to every financial report', 'Payment proof review before posting', 'Ageing buckets reconciled with Tally Prime'],
  },
  {
    icon: Smartphone,
    title: 'Field reps',
    body: 'A focused Android app for the day on the road.',
    points: ['Today’s route from the visit plan', 'Geofenced check-in, orders and payments', 'Offline queue that syncs automatically'],
  },
];

const STEPS = [
  { title: 'Plan', body: 'Admins build the monthly visit plan by territory, outlet and field officer.' },
  { title: 'Visit & verify', body: 'Reps check in on site; the app confirms they are inside the outlet’s geofence.' },
  { title: 'Capture', body: 'Orders, payments with proof, photos and customer requirements in one flow.' },
  { title: 'Sync & reconcile', body: 'Data lands on the dashboard in real time and is matched against Tally Prime.' },
];

const SECURITY = [
  { icon: Fingerprint, title: 'Role-based access', body: 'Super admin, admin and employee roles; employees only ever see their own customers and visits.' },
  { icon: KeyRound, title: 'Re-authentication for role changes', body: 'Promoting or demoting a user requires the super admin to confirm their password again.' },
  { icon: MapPin, title: 'Verified location', body: 'Visits are geofenced and time-stamped, so every check-in is backed by GPS evidence.' },
  { icon: Lock, title: 'Encrypted in transit and on device', body: 'HTTPS end to end, and the Android app keeps credentials in the device’s secure keystore.' },
  { icon: ScrollText, title: 'Approval trail', body: 'Payments, ad-hoc visits and outlet changes go through review, with who approved what and when.' },
  { icon: ShieldCheck, title: 'Read-only Tally link', body: 'The Tally agent reads financial data for reconciliation; field users never touch the ledger.' },
];

const FAQS = [
  { q: 'Who is FieldTrack Pro for?', a: 'Distribution and FMCG businesses that run field sales teams across many outlets and brands, and need visits, collections and accounts to line up.' },
  { q: 'Does it work without mobile signal?', a: 'Yes. The Android app queues visits, photos and payments offline and syncs them automatically once the device is back online.' },
  { q: 'How does the Tally integration work?', a: 'A small agent on your Tally server shares invoices, vouchers and receipts with FieldTrack Pro so collections and outstanding balances are reconciled against Tally Prime.' },
  { q: 'How do I install the Android app?', a: 'Tap “Download app” on your Android phone (Android 8.0 or later), open the downloaded file and allow your browser to install apps when Android asks. Then sign in with the account your admin created.' },
  { q: 'What can each role see?', a: 'Admins see every employee, territory, outlet and report. Accountants get read-only financial reports. Employees see only their own profile, assigned customers, visits and submissions.' },
  { q: 'Can I use it from a computer?', a: 'Yes. Admins and accountants use the web dashboard in any modern browser: choose “Use on web” and sign in.' },
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

/** Tracks which section is in view so the nav can underline it. */
function useActiveSection(ids: string[]): string {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: '-40% 0px -55% 0px', threshold: [0, 0.25, 0.5] },
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    });
    return () => io.disconnect();
  }, [ids]);
  return active;
}

const Logo: React.FC = () => (
  <span className="ftl-brand">
    <span className="ftl-brand-mark" aria-hidden="true">
      <ShieldCheck />
    </span>
    FieldTrack Pro
  </span>
);

const DownloadButton: React.FC<{ meta: ApkMetaFull | null; id?: string; variant?: 'outline' | 'primary' }> = ({
  meta,
  id,
  variant = 'outline',
}) => (
  <a
    id={id}
    href={APK_DOWNLOAD_URL}
    download={APK_DOWNLOAD_FILENAME}
    className={`ftl-btn ftl-btn--${variant} ftl-btn--lg`}
    data-testid="landing-download-apk"
  >
    <Download aria-hidden="true" />
    <span>
      Download app
      <small>Android{formatApkMeta(meta) ? ` · ${formatApkMeta(meta)}` : ''}</small>
    </span>
  </a>
);

const SECTION_IDS = NAV_LINKS.map((l) => l.id);

export const LandingPage: React.FC = () => {
  const reduced = usePrefersReducedMotion();
  const rootRef = useRef<HTMLDivElement>(null);
  const meta = useApkMeta();
  const active = useActiveSection(SECTION_IDS);
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useReveal(rootRef, reduced);

  useEffect(() => {
    const prevTitle = document.title;
    document.title = 'FieldTrack Pro — Unified field operations for multi-brand businesses';
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false);
    window.addEventListener('keydown', onKey);
    return () => {
      document.title = prevTitle;
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div ref={rootRef} className={`ftl${reduced ? ' ftl--still' : ''}`}>
      <a href="#main" className="ftl-skip">
        Skip to content
      </a>

      <header className={`ftl-nav${scrolled || menuOpen ? ' is-scrolled' : ''}`}>
        <div className="ftl-wrap ftl-nav-inner">
          <a href="#home" aria-label="FieldTrack Pro home" onClick={closeMenu}>
            <Logo />
          </a>
          <nav aria-label="Sections" className="ftl-nav-links">
            {NAV_LINKS.map((l) => (
              <a key={l.id} href={`#${l.id}`} className={active === l.id ? 'is-active' : ''} aria-current={active === l.id ? 'true' : undefined}>
                {l.label}
              </a>
            ))}
          </nav>
          <div className="ftl-nav-actions">
            <Link to="/login" className="ftl-btn ftl-btn--outline ftl-btn--nav">
              Login
            </Link>
            <a href="#get" className="ftl-btn ftl-btn--primary ftl-btn--nav">
              Get Started <ArrowRight aria-hidden="true" />
            </a>
          </div>
          <button
            type="button"
            className="ftl-menu-btn"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="ftl-mobile-menu"
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
        <div id="ftl-mobile-menu" className={`ftl-mobile-menu${menuOpen ? ' is-open' : ''}`} hidden={!menuOpen}>
          <div className="ftl-wrap">
            {NAV_LINKS.map((l) => (
              <a key={l.id} href={`#${l.id}`} onClick={closeMenu} className={active === l.id ? 'is-active' : ''}>
                {l.label}
              </a>
            ))}
            <div className="ftl-mobile-actions">
              <Link to="/login" className="ftl-btn ftl-btn--outline" onClick={closeMenu}>
                Login
              </Link>
              <a href="#get" className="ftl-btn ftl-btn--primary" onClick={closeMenu}>
                Get Started <ArrowRight aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>
      </header>

      <main id="main">
        {/* ---------- Hero ---------- */}
        <section id="home" className="ftl-hero" aria-labelledby="ftl-hero-title">
          <div className="ftl-glow-curve" aria-hidden="true" />
          <div className="ftl-wrap ftl-hero-grid">
            <div className="ftl-hero-copy">
              <p className="ftl-pill ftl-in" style={{ '--d': '0ms' } as React.CSSProperties}>
                <span className="ftl-pill-dot" /> Field Operations Intelligence
              </p>
              <h1 id="ftl-hero-title" className="ftl-in" style={{ '--d': '80ms' } as React.CSSProperties}>
                <span className="ftl-h1-line">Unified Field Operations</span> for{' '}
                <span className="ftl-accent">Multi-Brand Businesses</span>
              </h1>
              <p className="ftl-lead ftl-in" style={{ '--d': '160ms' } as React.CSSProperties}>
                A powerful platform to manage field teams, outlets, collections, visits and business operations — all in
                one place.
              </p>
              <div className="ftl-ctas ftl-in" style={{ '--d': '240ms' } as React.CSSProperties}>
                <div className="ftl-cta">
                  <Link to="/login" className="ftl-btn ftl-btn--primary ftl-btn--lg" data-testid="landing-use-web">
                    <Monitor aria-hidden="true" />
                    <span>Use on web</span>
                    <ArrowRight aria-hidden="true" className="ftl-btn-arrow" />
                  </Link>
                  <small>Web for admins and accountants</small>
                </div>
                <div className="ftl-cta">
                  <DownloadButton meta={meta} />
                  <small>Android app for field reps</small>
                </div>
              </div>
              <ul className="ftl-checks ftl-in" style={{ '--d': '320ms' } as React.CSSProperties}>
                {['Real-time Sync', 'Multi-Brand Support', 'Secure & Reliable'].map((c) => (
                  <li key={c}>
                    <Check aria-hidden="true" /> {c}
                  </li>
                ))}
              </ul>
            </div>
            <div className="ftl-hero-visual">
              <Suspense fallback={<div className="ftl-scene ftl-scene--placeholder" aria-hidden="true" />}>
                <DeviceScene reduced={reduced} />
              </Suspense>
            </div>
          </div>

          <div className="ftl-wrap">
            <ul className="ftl-strip">
              {STRIP.map(({ icon: Icon, title, body }, i) => (
                <li key={title} data-reveal style={{ '--d': `${i * 70}ms` } as React.CSSProperties}>
                  <span className="ftl-icon-tile">
                    <Icon aria-hidden="true" />
                  </span>
                  <div>
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------- Features ---------- */}
        <section id="features" className="ftl-section" aria-labelledby="ftl-features-title">
          <div className="ftl-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-kicker">Features</p>
              <h2 id="ftl-features-title">
                Everything your field operation runs on, <span className="ftl-accent">in one place</span>
              </h2>
              <p className="ftl-sub">From the first outlet visit of the day to the last receipt in Tally.</p>
            </div>
            <div className="ftl-cards">
              {FEATURES.map(({ icon: Icon, title, body }, i) => (
                <article key={title} className="ftl-card" data-reveal style={{ '--d': `${(i % 4) * 70}ms` } as React.CSSProperties}>
                  <span className="ftl-icon-tile">
                    <Icon aria-hidden="true" />
                  </span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ---------- Solutions ---------- */}
        <section id="solutions" className="ftl-section ftl-section--alt" aria-labelledby="ftl-solutions-title">
          <div className="ftl-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-kicker">Solutions</p>
              <h2 id="ftl-solutions-title">
                Built for every seat in a <span className="ftl-accent">multi-brand business</span>
              </h2>
            </div>
            <div className="ftl-solutions">
              {SOLUTIONS.map(({ icon: Icon, title, body, points }, i) => (
                <article key={title} className="ftl-card ftl-card--tall" data-reveal style={{ '--d': `${i * 80}ms` } as React.CSSProperties}>
                  <span className="ftl-icon-tile ftl-icon-tile--lg">
                    <Icon aria-hidden="true" />
                  </span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  <ul>
                    {points.map((p) => (
                      <li key={p}>
                        <Check aria-hidden="true" /> {p}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ---------- How it works ---------- */}
        <section id="how" className="ftl-section" aria-labelledby="ftl-how-title">
          <div className="ftl-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-kicker">How It Works</p>
              <h2 id="ftl-how-title">
                From plan to ledger in <span className="ftl-accent">four steps</span>
              </h2>
            </div>
            <ol className="ftl-steps">
              {STEPS.map((s, i) => (
                <li key={s.title} data-reveal style={{ '--d': `${i * 90}ms` } as React.CSSProperties}>
                  <span className="ftl-step-num">{String(i + 1).padStart(2, '0')}</span>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ---------- Security ---------- */}
        <section id="security" className="ftl-section ftl-section--alt" aria-labelledby="ftl-security-title">
          <div className="ftl-wrap ftl-security">
            <div className="ftl-head ftl-head--left" data-reveal>
              <p className="ftl-kicker">Security</p>
              <h2 id="ftl-security-title">
                Secure by design, <span className="ftl-accent">reliable by default</span>
              </h2>
              <p className="ftl-sub">
                Field data, collections and financial records are protected by strict roles, verified locations and
                encrypted connections.
              </p>
              <span className="ftl-shield" aria-hidden="true">
                <ShieldCheck />
              </span>
            </div>
            <div className="ftl-sec-grid">
              {SECURITY.map(({ icon: Icon, title, body }, i) => (
                <div key={title} className="ftl-sec-item" data-reveal style={{ '--d': `${(i % 2) * 80}ms` } as React.CSSProperties}>
                  <span className="ftl-icon-tile ftl-icon-tile--sm">
                    <Icon aria-hidden="true" />
                  </span>
                  <div>
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---------- FAQ ---------- */}
        <section id="faq" className="ftl-section" aria-labelledby="ftl-faq-title">
          <div className="ftl-wrap ftl-faq-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-kicker">FAQ</p>
              <h2 id="ftl-faq-title">Frequently asked questions</h2>
            </div>
            <div className="ftl-faq">
              {FAQS.map((f) => (
                <details key={f.q} data-reveal>
                  <summary>
                    {f.q}
                    <ChevronDown aria-hidden="true" />
                  </summary>
                  <p>{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* ---------- Get started ---------- */}
        <section id="get" className="ftl-section ftl-section--alt" aria-labelledby="ftl-get-title">
          <div className="ftl-wrap">
            <div className="ftl-head" data-reveal>
              <p className="ftl-kicker">Get Started</p>
              <h2 id="ftl-get-title">
                Pick your <span className="ftl-accent">screen</span>
              </h2>
            </div>
            <div className="ftl-get">
              <div className="ftl-get-card" data-reveal>
                <span className="ftl-icon-tile ftl-icon-tile--lg">
                  <Monitor aria-hidden="true" />
                </span>
                <h3>Use on web</h3>
                <p>
                  The admin dashboard for owners, managers and accountants: territories, employees, visit plans,
                  collections and reports. Works in any modern browser.
                </p>
                <Link to="/login" className="ftl-btn ftl-btn--primary ftl-btn--lg">
                  <span>Sign in on the web</span>
                  <ArrowRight aria-hidden="true" className="ftl-btn-arrow" />
                </Link>
              </div>
              <div className="ftl-get-card" data-reveal style={{ '--d': '90ms' } as React.CSSProperties}>
                <span className="ftl-icon-tile ftl-icon-tile--lg">
                  <Smartphone aria-hidden="true" />
                </span>
                <h3>Android app</h3>
                <p>For field reps: today’s route, geofenced check-ins, orders, payments and photos, even offline. Android 8.0 or later.</p>
                <DownloadButton meta={meta} id="download" variant="primary" />
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
                  Installed directly, not from Google Play: when Android asks, allow your browser to install apps from this source.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="ftl-footer">
        <div className="ftl-wrap ftl-footer-grid">
          <div>
            <Logo />
            <p>Unified field operations for multi-brand businesses.</p>
          </div>
          <nav aria-label="Footer">
            <h4>Product</h4>
            <a href="#features">Features</a>
            <a href="#solutions">Solutions</a>
            <a href="#how">How It Works</a>
          </nav>
          <nav aria-label="Trust">
            <h4>Trust</h4>
            <a href="#security">Security</a>
            <a href="#faq">FAQ</a>
          </nav>
          <nav aria-label="Get the app">
            <h4>Get started</h4>
            <Link to="/login">Use on web</Link>
            <a href={APK_DOWNLOAD_URL} download={APK_DOWNLOAD_FILENAME}>
              Download Android app
            </a>
          </nav>
        </div>
        <div className="ftl-wrap ftl-footer-base">
          <span>© {new Date().getFullYear()} FieldTrack Pro. All rights reserved.</span>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;

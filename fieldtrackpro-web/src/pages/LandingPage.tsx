import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Download, Menu, Plus, X } from 'lucide-react';
import { APK_DOWNLOAD_FILENAME, APK_DOWNLOAD_URL, APK_META_PATH, formatApkMeta } from '../config/apk';
import { Hero } from '../components/landing/Hero';
import { Bento } from '../components/landing/Bento';
import { usePrefersReducedMotion, useReveal, useScrollProgress, useSmoothScroll } from '../components/landing/motion';
import '../components/landing/landing.css';

interface ApkMetaFull {
  versionName?: string;
  versionCode?: number;
  sizeBytes?: number;
  sha256?: string;
}

const FONT_HREF =
  'https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap';

const NAV = [
  { href: '#product', label: 'Product' },
  { href: '#how', label: 'How it works' },
  { href: '#security', label: 'Security' },
  { href: '#faq', label: 'FAQ' },
];

const STEPS = [
  {
    k: 'Plan',
    title: 'Plan the month by territory.',
    body: 'Admins assign outlets to field officers and build the monthly visit plan. Each rep wakes up to today’s route on their phone.',
  },
  {
    k: 'Verify',
    title: 'Verify every visit on site.',
    body: 'The app only opens a visit inside the outlet’s geofence, then captures orders, payments with proof, photos and requirements.',
  },
  {
    k: 'Reconcile',
    title: 'Reconcile against Tally Prime.',
    body: 'Collections land on the dashboard in real time and are matched to vouchers in Tally, so outstanding and ageing stay true.',
  },
];

const SECURITY = [
  ['Roles', 'Super admin, admin and employee. Employees only ever see their own profile, customers, visits and submissions.'],
  ['Role changes', 'Promoting or demoting a user requires the super admin to re-authenticate.'],
  ['Location', 'Visits are geofenced and time-stamped; every check-in carries GPS accuracy evidence.'],
  ['Transport', 'HTTPS end to end. The Android app keeps credentials in the device keystore.'],
  ['Approvals', 'Payments, ad-hoc visits and outlet changes are reviewed, with who approved what and when.'],
  ['Ledger', 'The Tally agent reads financial data for reconciliation; field users never write to the ledger.'],
];

const FAQS = [
  ['Who is FieldTrack Pro for?', 'Distribution and FMCG businesses running field sales teams across many outlets and brands, who need visits, collections and accounts to agree.'],
  ['Does it work without mobile signal?', 'Yes. The Android app queues visits, photos and payments offline and syncs them automatically when the phone is back online.'],
  ['How does the Tally integration work?', 'A small agent on your Tally server shares invoices, vouchers and receipts, so collections and outstanding balances reconcile against Tally Prime.'],
  ['How do I install the Android app?', 'On an Android phone (8.0 or later), tap “Download app”, open the file and allow your browser to install apps when Android asks. Sign in with the account your admin created.'],
  ['What can each role see?', 'Admins see every employee, territory, outlet and report; accountants get read-only financial reports; employees see only their own work.'],
  ['Can I use it from a computer?', 'Yes. Admins and accountants use the web dashboard in any modern browser: choose “Use on web” and sign in.'],
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

/** Load the landing page's typefaces only on this page. */
function usePageFonts() {
  useEffect(() => {
    if (document.querySelector(`link[data-ftl-fonts]`)) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = FONT_HREF;
    l.dataset.ftlFonts = '1';
    document.head.appendChild(l);
  }, []);
}

const AUTHOR_URL = 'https://github.com/itripathiharsh';

/** The FieldTrack Pro logo (same artwork as public/favicon.svg). */
const Wordmark: React.FC = () => (
  <span className="ftl-wordmark">
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#14213d" />
      <path d="M16 5L6.5 9V16C6.5 21 10.8 25.5 16 27C21.2 25.5 25.5 21 25.5 16V9Z" stroke="#ffa515" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M11 16.5L14.5 20L21 13" stroke="#ffa515" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
    FieldTrack Pro
  </span>
);

/* ---------- Pinned "How it works" ---------- */

const StepVisual: React.FC<{ step: number }> = ({ step }) => (
  <div className="ftl-step-visual" data-step={step}>
    <div className={`ftl-sv ftl-sv--plan${step === 0 ? ' is-on' : ''}`} aria-hidden="true">
      <div className="ftl-sv-head ftl-mono">
        <span>Visit plan · Demo month</span>
        <span>Zone North</span>
      </div>
      <div className="ftl-cal">
        {Array.from({ length: 35 }, (_, i) => (
          <span key={i} className={[3, 4, 8, 10, 11, 15, 17, 18, 22, 24, 25, 29].includes(i) ? 'has' : ''} style={{ '--i': i } as React.CSSProperties}>
            {i + 1 <= 31 ? i + 1 : ''}
          </span>
        ))}
      </div>
    </div>
    <div className={`ftl-sv ftl-sv--verify${step === 1 ? ' is-on' : ''}`} aria-hidden="true">
      <div className="ftl-sv-head ftl-mono">
        <span>Outlet 0388</span>
        <span className="ok">Inside fence · 12 m</span>
      </div>
      <div className="ftl-sv-radar">
        <i />
        <i />
        <b />
      </div>
      <div className="ftl-sv-rows">
        <div>
          <span>Order items</span>
          <b>14</b>
        </div>
        <div>
          <span>Payment · UPI</span>
          <b>₹4,200</b>
        </div>
        <div>
          <span>Shelf photo</span>
          <b>Attached</b>
        </div>
      </div>
    </div>
    <div className={`ftl-sv ftl-sv--rec${step === 2 ? ' is-on' : ''}`} aria-hidden="true">
      <div className="ftl-sv-head ftl-mono">
        <span>Field</span>
        <span>Tally Prime</span>
      </div>
      {[
        ['UPI ₹4,200', 'RCPT-0416'],
        ['Cash ₹1,850', 'RCPT-0417'],
        ['Cheque ₹22,000', 'CHQ-0088'],
        ['UPI ₹9,600', 'RCPT-0418'],
      ].map(([a, b], i) => (
        <div key={a} className="ftl-rec-row" style={{ '--i': i } as React.CSSProperties}>
          <span>{a}</span>
          <i />
          <span>{b}</span>
        </div>
      ))}
    </div>
  </div>
);

const HowItWorks: React.FC = () => {
  const ref = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  useScrollProgress(ref, STEPS.length, useCallback((i: number) => setStep(i), []));
  return (
    <section id="how" ref={ref} className="ftl-how" aria-labelledby="ftl-how-title">
      <div className="ftl-how-pin">
        <div className="ftl-wrap ftl-how-grid">
          <div className="ftl-how-copy">
            <span className="ftl-mono ftl-kicker">How it works</span>
            <h2 id="ftl-how-title" className="ftl-h2">
              Three steps from
              <br />
              outlet to ledger.
            </h2>
            <ol className="ftl-how-steps">
              {STEPS.map((s, i) => (
                <li key={s.k} className={i === step ? 'is-active' : i < step ? 'is-done' : ''}>
                  <span className="ftl-mono">0{i + 1}</span>
                  <div>
                    <h3>{s.title}</h3>
                    <p>{s.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="ftl-how-bar" aria-hidden="true">
              <span />
            </div>
          </div>
          <StepVisual step={step} />
        </div>
      </div>
    </section>
  );
};

/* ---------- Page ---------- */

export const LandingPage: React.FC = () => {
  const reduced = usePrefersReducedMotion();
  const rootRef = useRef<HTMLDivElement>(null);
  const meta = useApkMeta();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  usePageFonts();
  useReveal(rootRef, reduced);
  useSmoothScroll(!reduced);

  useEffect(() => {
    const prevTitle = document.title;
    document.title = 'FieldTrack Pro — Field operations, live';
    const onScroll = () => setScrolled(window.scrollY > 8);
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

  const close = () => setMenuOpen(false);
  const apk = formatApkMeta(meta);

  return (
    <div ref={rootRef} className={`ftl${reduced ? ' ftl--still' : ''}`}>
      <div className="ftl-grain" aria-hidden="true" />
      <a href="#main" className="ftl-skip">
        Skip to content
      </a>

      <header className={`ftl-nav${scrolled || menuOpen ? ' is-solid' : ''}`}>
        <div className="ftl-wrap ftl-nav-row">
          <a href="#top" aria-label="FieldTrack Pro home" onClick={close}>
            <Wordmark />
          </a>
          <nav aria-label="Sections" className="ftl-nav-links">
            {NAV.map((n) => (
              <a key={n.href} href={n.href}>
                {n.label}
              </a>
            ))}
          </nav>
          <div className="ftl-nav-cta">
            <Link to="/login" className="ftl-navlink">
              Log in
            </Link>
            <a href="#get" className="ftl-btn ftl-btn--solid ftl-btn--sm">
              Get the app
            </a>
          </div>
          <button
            type="button"
            className="ftl-burger"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="ftl-menu"
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
        <div id="ftl-menu" className="ftl-menu" hidden={!menuOpen}>
          <div className="ftl-wrap">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} onClick={close}>
                {n.label}
              </a>
            ))}
            <div className="ftl-menu-cta">
              <Link to="/login" className="ftl-btn ftl-btn--line" onClick={close}>
                Log in
              </Link>
              <a href="#get" className="ftl-btn ftl-btn--solid" onClick={close}>
                Get the app
              </a>
            </div>
          </div>
        </div>
      </header>

      <main id="main">
        <Hero reduced={reduced} meta={meta} />

        <section id="product" className="ftl-sec" aria-labelledby="ftl-product-title">
          <div className="ftl-wrap">
            <div className="ftl-sec-head" data-reveal>
              <span className="ftl-mono ftl-kicker">Product</span>
              <h2 id="ftl-product-title" className="ftl-h2">
                One system from the shop floor
                <br />
                <span className="ftl-dim">to the ledger.</span>
              </h2>
            </div>
            <Bento reduced={reduced} />
          </div>
        </section>

        <HowItWorks />

        <section id="security" className="ftl-sec" aria-labelledby="ftl-security-title">
          <div className="ftl-wrap ftl-split">
            <div className="ftl-sec-head ftl-sec-head--side" data-reveal>
              <span className="ftl-mono ftl-kicker">Security</span>
              <h2 id="ftl-security-title" className="ftl-h2">
                Built for data
                <br />
                <span className="ftl-dim">you’re accountable for.</span>
              </h2>
            </div>
            <dl className="ftl-spec" data-reveal>
              {SECURITY.map(([k, v]) => (
                <div key={k}>
                  <dt className="ftl-mono">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section id="faq" className="ftl-sec" aria-labelledby="ftl-faq-title">
          <div className="ftl-wrap ftl-split">
            <div className="ftl-sec-head ftl-sec-head--side" data-reveal>
              <span className="ftl-mono ftl-kicker">FAQ</span>
              <h2 id="ftl-faq-title" className="ftl-h2">Questions, answered.</h2>
            </div>
            <div className="ftl-faq">
              {FAQS.map(([q, a]) => (
                <details key={q}>
                  <summary>
                    {q}
                    <Plus aria-hidden="true" />
                  </summary>
                  <p>{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section id="get" className="ftl-final" aria-labelledby="ftl-get-title">
          <div className="ftl-wrap">
            <h2 id="ftl-get-title" className="ftl-final-title" data-reveal>
              Put your field
              <br />
              on the map.
            </h2>
            <div className="ftl-final-grid" data-reveal>
              <div className="ftl-final-card">
                <span className="ftl-mono">Web · admins & accountants</span>
                <p>Territories, employees, visit plans, collections and reports in any modern browser.</p>
                <Link to="/login" className="ftl-btn ftl-btn--solid">
                  Use on web <ArrowRight aria-hidden="true" />
                </Link>
              </div>
              <div className="ftl-final-card">
                <span className="ftl-mono">Android · field reps</span>
                <p>Today’s route, geofenced check-ins, orders, payments and photos, even offline. Android 8.0+.</p>
                <a id="download" href={APK_DOWNLOAD_URL} download={APK_DOWNLOAD_FILENAME} className="ftl-btn ftl-btn--line" data-testid="landing-download-apk">
                  <Download aria-hidden="true" />
                  <span>
                    Download app
                    <small>Android{apk ? ` · ${apk}` : ''}</small>
                  </span>
                </a>
                <dl className="ftl-apk">
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
                <p className="ftl-fine">Installed directly, not from Google Play: allow your browser to install apps when Android asks.</p>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="ftl-foot">
        <div className="ftl-wrap ftl-foot-row">
          <Wordmark />
          <nav aria-label="Footer">
            {NAV.map((n) => (
              <a key={n.href} href={n.href}>
                {n.label}
              </a>
            ))}
            <Link to="/login">Log in</Link>
          </nav>
          <a href={AUTHOR_URL} target="_blank" rel="noopener noreferrer">
            Contact
          </a>
        </div>
        <div className="ftl-wrap ftl-foot-credit">
          <span>© {new Date().getFullYear()} FieldTrack Pro</span>
          <span>
            Made by{' '}
            <a href={AUTHOR_URL} target="_blank" rel="noopener noreferrer">
              Harsh Vardhan Tripathi
            </a>
          </span>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;

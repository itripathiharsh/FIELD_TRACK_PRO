import React, { useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
import { useInView } from './motion';

/* All figures in this file are demo data. */

const ROUTE_D = 'M24 196 H96 V128 H196 V64 H300 V140 H372';

const RouteCell: React.FC<{ live: boolean }> = ({ live }) => (
  <div className="ftl-bento-viz ftl-route">
    <svg viewBox="0 0 400 230" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <pattern id="ftl-streets" width="52" height="52" patternUnits="userSpaceOnUse">
          <path d="M52 0H0V52" fill="none" stroke="rgba(255,255,255,.06)" strokeWidth="10" />
        </pattern>
      </defs>
      <rect width="400" height="230" fill="url(#ftl-streets)" />
      <path d={ROUTE_D} fill="none" stroke="rgba(255,255,255,.14)" strokeWidth="4" strokeLinejoin="round" />
      <path
        d={ROUTE_D}
        fill="none"
        stroke="#ff9f2e"
        strokeWidth="4"
        strokeLinejoin="round"
        pathLength={1}
        className={live ? 'ftl-route-draw' : ''}
        strokeDasharray={live ? undefined : '1 0'}
      />
      {[
        [96, 128],
        [196, 64],
        [300, 140],
      ].map(([x, y], i) => (
        <g key={i} className="ftl-route-stop" style={{ '--i': i } as React.CSSProperties}>
          <circle cx={x} cy={y} r="11" fill="#0b0b0d" stroke="#ededed" strokeOpacity=".35" />
          <circle cx={x} cy={y} r="4" fill="#ededed" />
        </g>
      ))}
      <circle r="7" fill="#ff9f2e">
        {live ? <animateMotion dur="7s" repeatCount="indefinite" path={ROUTE_D} keyPoints="0;1" keyTimes="0;1" calcMode="linear" /> : null}
      </circle>
      {!live && <circle cx="196" cy="64" r="7" fill="#ff9f2e" />}
    </svg>
    <div className="ftl-viz-tags">
      <span>REP-07</span>
      <span>4 / 6 visits</span>
      <span>ETA 11:40</span>
    </div>
  </div>
);

const CheckinCell: React.FC<{ live: boolean }> = ({ live }) => {
  const [d, setD] = useState(live ? 64 : 12);
  useEffect(() => {
    if (!live) {
      setD(12);
      return;
    }
    let v = 64;
    const id = window.setInterval(() => {
      v = v <= 12 ? 64 : Math.max(12, v - 4);
      setD(v);
    }, 180);
    return () => window.clearInterval(id);
  }, [live]);
  const ok = d <= 50;
  return (
    <div className="ftl-bento-viz ftl-geo">
      <div className="ftl-geo-field" aria-hidden="true">
        <span className="ftl-geo-fence" />
        <span className="ftl-geo-outlet" />
        <span className="ftl-geo-rep" style={{ '--d': d } as React.CSSProperties} />
      </div>
      <div className={`ftl-geo-read${ok ? ' is-ok' : ''}`}>
        <span className="ftl-mono">{String(d).padStart(2, '0')} m</span>
        <b>{ok ? 'Inside geofence' : 'Approaching outlet'}</b>
        <small>{ok ? <><Check aria-hidden="true" /> Check-in allowed</> : 'Fence 50 m · ±4 m GPS'}</small>
      </div>
    </div>
  );
};

const VOUCHERS = [
  ['RCPT-0412', '₹12,400', 'Matched'],
  ['RCPT-0413', '₹3,150', 'Matched'],
  ['INV-2291', '₹48,900', 'Synced'],
  ['RCPT-0414', '₹7,800', 'Matched'],
  ['CHQ-0087', '₹22,000', 'Pending'],
  ['RCPT-0415', '₹1,960', 'Matched'],
  ['INV-2292', '₹15,300', 'Synced'],
];

const TallyCell: React.FC<{ live: boolean }> = ({ live }) => (
  <div className={`ftl-bento-viz ftl-ticker${live ? ' is-live' : ''}`}>
    <div className="ftl-ticker-track">
      {[...VOUCHERS, ...VOUCHERS].map(([id, amt, st], i) => (
        <div key={i} className="ftl-ticker-row" aria-hidden={i >= VOUCHERS.length ? true : undefined}>
          <span>{id}</span>
          <span>{amt}</span>
          <span className={`is-${st.toLowerCase()}`}>{st}</span>
        </div>
      ))}
    </div>
  </div>
);

const BUCKETS = [
  ['0–30', 62, '₹4.1L'],
  ['31–60', 38, '₹2.5L'],
  ['61–90', 21, '₹1.4L'],
  ['90+', 12, '₹0.8L'],
] as const;

const AgeingCell: React.FC<{ show: boolean }> = ({ show }) => (
  <div className={`ftl-bento-viz ftl-ageing${show ? ' is-in' : ''}`}>
    {BUCKETS.map(([label, h, amt], i) => (
      <div key={label} className="ftl-ageing-col">
        <small className="ftl-mono">{amt}</small>
        <div className="ftl-ageing-bar">
          <span style={{ '--h': `${h}%`, '--i': i } as React.CSSProperties} className={i === 3 ? 'is-hot' : ''} />
        </div>
        <span className="ftl-mono">{label}</span>
      </div>
    ))}
  </div>
);

const OfflineCell: React.FC<{ live: boolean }> = ({ live }) => {
  const [q, setQ] = useState(3);
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setQ((v) => (v === 0 ? 3 : v - 1)), 1100);
    return () => window.clearInterval(id);
  }, [live]);
  return (
    <div className="ftl-bento-viz ftl-queue">
      <div className="ftl-queue-items" aria-hidden="true">
        {['Visit · 0388', 'Photo · shelf', 'UPI · ₹4,200'].map((t, i) => (
          <span key={t} className={i < q ? 'is-queued' : 'is-sent'}>
            {t}
          </span>
        ))}
      </div>
      <div className="ftl-queue-state ftl-mono">{q === 0 ? 'All synced' : `${q} queued · no signal`}</div>
    </div>
  );
};

const ROLES = [
  ['Super admin', 'Roles & protected ops'],
  ['Admin', 'Every territory & report'],
  ['Employee', 'Own route & customers'],
];

const RolesCell: React.FC = () => (
  <div className="ftl-bento-viz ftl-roles">
    {ROLES.map(([r, s], i) => (
      <div key={r} className="ftl-role" style={{ '--i': i } as React.CSSProperties}>
        <b>{r}</b>
        <span>{s}</span>
      </div>
    ))}
  </div>
);

export const Bento: React.FC<{ reduced: boolean }> = ({ reduced }) => {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, '0px 0px -15% 0px');
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (inView) setSeen(true);
  }, [inView]);
  const live = !reduced && inView;

  return (
    <div ref={ref} className="ftl-bento">
      <article className="ftl-cell ftl-cell--route" data-reveal>
        <header>
          <span className="ftl-mono">01 · Routes</span>
          <h3>Plan the month, follow the day.</h3>
          <p>Monthly visit plans per territory become each rep’s route, tracked planned versus actual.</p>
        </header>
        <RouteCell live={live} />
      </article>
      <article className="ftl-cell ftl-cell--geo" data-reveal style={{ '--d': '80ms' } as React.CSSProperties}>
        <header>
          <span className="ftl-mono">02 · Verification</span>
          <h3>Check-ins only count on site.</h3>
        </header>
        <CheckinCell live={live} />
      </article>
      <article className="ftl-cell ftl-cell--tally" data-reveal style={{ '--d': '160ms' } as React.CSSProperties}>
        <header>
          <span className="ftl-mono">03 · Tally Prime</span>
          <h3>Receipts matched to the ledger.</h3>
        </header>
        <TallyCell live={live} />
      </article>
      <article className="ftl-cell ftl-cell--ageing" data-reveal>
        <header>
          <span className="ftl-mono">04 · Outstanding</span>
          <h3>Ageing you can act on.</h3>
          <p>Overdue by bucket, brand, zone and field officer.</p>
        </header>
        <AgeingCell show={seen || reduced} />
      </article>
      <article className="ftl-cell ftl-cell--queue" data-reveal style={{ '--d': '80ms' } as React.CSSProperties}>
        <header>
          <span className="ftl-mono">05 · Offline</span>
          <h3>No signal, no problem.</h3>
        </header>
        <OfflineCell live={live} />
      </article>
      <article className="ftl-cell ftl-cell--roles" data-reveal style={{ '--d': '160ms' } as React.CSSProperties}>
        <header>
          <span className="ftl-mono">06 · Access</span>
          <h3>Everyone sees exactly their part.</h3>
        </header>
        <RolesCell />
      </article>
    </div>
  );
};

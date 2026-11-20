import React from 'react';
import {
  BarChart3,
  CalendarDays,
  Camera,
  CheckCircle2,
  ClipboardList,
  Home,
  IndianRupee,
  LayoutDashboard,
  Map as MapIcon,
  MapPin,
  Navigation,
  RefreshCw,
  Users,
} from 'lucide-react';

/*
 * Illustrative, hand-built mockups of the FieldTrack Pro admin dashboard and the
 * Android app. Every name and figure here is sample copy for the marketing page,
 * not data from the system.
 */

const NAV = [
  { icon: LayoutDashboard, label: 'Dashboard', active: true },
  { icon: Users, label: 'Employees' },
  { icon: MapIcon, label: 'Live map' },
  { icon: CalendarDays, label: 'Visit plan' },
  { icon: IndianRupee, label: 'Collections' },
  { icon: BarChart3, label: 'Reports' },
];

const KPIS = [
  { label: 'Visits today', value: '128', delta: '+12%' },
  { label: 'GPS verified', value: '97%', delta: '+3%' },
  { label: 'Collected', value: '₹4.8L', delta: '+18%' },
  { label: 'Open requests', value: '23', delta: '−5' },
];

const BARS = [42, 64, 51, 78, 69, 88, 74];

/** Mini map: stylised roads, an animated route and pulsing visit pins. */
export const MiniMap: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`ftl-map ${className}`}>
    <svg viewBox="0 0 300 170" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <pattern id="ftl-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke="rgba(148,175,210,.10)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect width="300" height="170" fill="url(#ftl-grid)" />
      <path d="M0 120 C60 110 90 60 150 70 S250 30 300 40" stroke="rgba(148,175,210,.28)" strokeWidth="7" fill="none" />
      <path d="M40 0 C60 60 50 120 80 170" stroke="rgba(148,175,210,.2)" strokeWidth="5" fill="none" />
      <path d="M210 0 C200 60 230 110 220 170" stroke="rgba(148,175,210,.2)" strokeWidth="5" fill="none" />
      <path
        className="ftl-route"
        d="M48 132 C80 118 98 82 140 76 S205 64 228 48 S262 36 272 30"
        stroke="#ffa31e"
        strokeWidth="2.5"
        strokeDasharray="6 6"
        fill="none"
      />
    </svg>
    {[
      { x: 16, y: 77, c: 'ok' },
      { x: 46, y: 45, c: 'ok' },
      { x: 76, y: 28, c: 'live' },
      { x: 90, y: 18, c: 'next' },
    ].map((p, i) => (
      <span key={i} className={`ftl-pin ftl-pin--${p.c}`} style={{ left: `${p.x}%`, top: `${p.y}%` }}>
        <MapPin aria-hidden="true" />
      </span>
    ))}
  </div>
);

export const DesktopScreen: React.FC = () => (
  <div className="ftl-desk-ui">
    <aside className="ftl-desk-side">
      <div className="ftl-desk-logo">
        <span className="ftl-logo-dot" /> FieldTrack
      </div>
      {NAV.map(({ icon: Icon, label, active }) => (
        <div key={label} className={`ftl-desk-nav${active ? ' is-active' : ''}`}>
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </div>
      ))}
    </aside>
    <div className="ftl-desk-main">
      <div className="ftl-desk-top">
        <div>
          <div className="ftl-desk-kicker">Admin dashboard</div>
          <div className="ftl-desk-title">Field operations · Today</div>
        </div>
        <div className="ftl-desk-sync">
          <RefreshCw aria-hidden="true" /> Tally synced
        </div>
      </div>
      <div className="ftl-desk-kpis">
        {KPIS.map((k) => (
          <div key={k.label} className="ftl-kpi">
            <div className="ftl-kpi-label">{k.label}</div>
            <div className="ftl-kpi-value">{k.value}</div>
            <div className="ftl-kpi-delta">{k.delta}</div>
          </div>
        ))}
      </div>
      <div className="ftl-desk-panels">
        <div className="ftl-panel">
          <div className="ftl-panel-title">Live field map</div>
          <MiniMap />
        </div>
        <div className="ftl-panel">
          <div className="ftl-panel-title">Collections · 7 days</div>
          <div className="ftl-bars">
            {BARS.map((h, i) => (
              <span key={i} style={{ '--h': `${h}%`, '--i': i } as React.CSSProperties} />
            ))}
          </div>
        </div>
      </div>
    </div>
  </div>
);

type PhoneView = 'route' | 'checkin' | 'capture' | 'sync';

const VISITS = [
  { name: 'Outlet 0214 · Market Rd', time: '09:30', status: 'Done' },
  { name: 'Outlet 0388 · Station Sq', time: '11:00', status: 'Now' },
  { name: 'Outlet 0521 · Ring Rd', time: '12:45', status: 'Next' },
  { name: 'Outlet 0607 · Bazaar', time: '14:15', status: 'Next' },
];

const StatusBar: React.FC = () => (
  <div className="ftl-ph-status">
    <span>9:41</span>
    <span className="ftl-ph-notch" />
    <span>5G ▮▮▮</span>
  </div>
);

const BottomNav: React.FC = () => (
  <div className="ftl-ph-nav">
    <Home aria-hidden="true" />
    <CalendarDays aria-hidden="true" className="is-active" />
    <MapIcon aria-hidden="true" />
    <ClipboardList aria-hidden="true" />
  </div>
);

/** Android app screens. `view` selects which one is shown (used by the scroll story). */
export const PhoneScreen: React.FC<{ view?: PhoneView }> = ({ view = 'route' }) => (
  <div className="ftl-ph-ui">
    <StatusBar />
    {view === 'route' && (
      <div className="ftl-ph-body" key="route">
        <div className="ftl-ph-kicker">Today’s route</div>
        <div className="ftl-ph-title">4 visits planned</div>
        <div className="ftl-ph-progress">
          <span style={{ width: '38%' }} />
        </div>
        {VISITS.map((v) => (
          <div key={v.name} className={`ftl-ph-visit is-${v.status.toLowerCase()}`}>
            <div>
              <div className="ftl-ph-visit-name">{v.name}</div>
              <div className="ftl-ph-visit-time">{v.time}</div>
            </div>
            <span className="ftl-ph-pill">{v.status}</span>
          </div>
        ))}
        <button type="button" tabIndex={-1} className="ftl-ph-cta">
          <Navigation aria-hidden="true" /> Check in here
        </button>
      </div>
    )}
    {view === 'checkin' && (
      <div className="ftl-ph-body" key="checkin">
        <div className="ftl-ph-kicker">Check-in</div>
        <div className="ftl-ph-title">Outlet 0388</div>
        <div className="ftl-ph-radar">
          <span className="ftl-ph-ring" />
          <span className="ftl-ph-ring ftl-ph-ring--2" />
          <MapPin aria-hidden="true" />
        </div>
        <div className="ftl-ph-ok">
          <CheckCircle2 aria-hidden="true" /> Inside geofence · 12 m
        </div>
        <div className="ftl-ph-meta">GPS accuracy ±4 m · 11:02</div>
      </div>
    )}
    {view === 'capture' && (
      <div className="ftl-ph-body" key="capture">
        <div className="ftl-ph-kicker">Visit · Outlet 0388</div>
        <div className="ftl-ph-title">Order & payment</div>
        <div className="ftl-ph-photo">
          <Camera aria-hidden="true" /> Shelf photo attached
        </div>
        <div className="ftl-ph-row">
          <span>Order items</span>
          <b>14</b>
        </div>
        <div className="ftl-ph-row">
          <span>Payment · UPI</span>
          <b>₹ 48,200</b>
        </div>
        <div className="ftl-ph-row">
          <span>Requirement</span>
          <b>2 new SKUs</b>
        </div>
        <button type="button" tabIndex={-1} className="ftl-ph-cta">
          Submit visit
        </button>
      </div>
    )}
    {view === 'sync' && (
      <div className="ftl-ph-body" key="sync">
        <div className="ftl-ph-kicker">Sync</div>
        <div className="ftl-ph-title">All caught up</div>
        <div className="ftl-ph-synced">
          <RefreshCw aria-hidden="true" />
        </div>
        <div className="ftl-ph-row">
          <span>Visits uploaded</span>
          <b>4 / 4</b>
        </div>
        <div className="ftl-ph-row">
          <span>Receipt sent to Tally</span>
          <b className="ftl-ok-text">Matched</b>
        </div>
        <div className="ftl-ph-meta">Worked offline? The queue syncs when you’re back online.</div>
      </div>
    )}
    <BottomNav />
  </div>
);

export type { PhoneView };

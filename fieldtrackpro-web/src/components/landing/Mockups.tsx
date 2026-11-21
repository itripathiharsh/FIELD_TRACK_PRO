import React from 'react';
import {
  BarChart3,
  Bell,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileText,
  IndianRupee,
  LayoutDashboard,
  ListChecks,
  Lock,
  Map as MapIcon,
  MapPin,
  Settings,
  ShieldCheck,
  Store,
  UserCog,
  Users,
} from 'lucide-react';

/*
 * Illustrative mockup of the FieldTrack Pro admin dashboard for the public landing page.
 * Every company name, count and amount below is DEMO copy, not data from the system.
 */

const NAV: { icon: React.ElementType; label: string }[] = [
  { icon: LayoutDashboard, label: 'Dashboard' },
  { icon: CalendarDays, label: 'Visit Planning' },
  { icon: Users, label: 'Employees' },
  { icon: ListChecks, label: 'Employee Daily Logs' },
  { icon: MapIcon, label: 'Territories' },
  { icon: Store, label: 'Customers' },
  { icon: ClipboardCheck, label: 'Outlet Verification' },
  { icon: MapPin, label: 'Outlet Mapping' },
  { icon: CalendarDays, label: 'Visits' },
  { icon: UserCog, label: 'Ad-hoc Review' },
  { icon: MapIcon, label: 'Map' },
  { icon: ClipboardList, label: 'Customer Requirements' },
  { icon: FileText, label: 'Requirement Forms' },
  { icon: IndianRupee, label: 'Payment Collections' },
  { icon: BarChart3, label: 'Reports & Collections' },
];

const FILTERS = [
  ['Period / Month', 'Current Live Data'],
  ['Brand', 'All Brands'],
  ['Zone (Territory)', 'All Zones'],
  ['Area', 'All Areas'],
  ['FOS / Field Officer', 'All Field Officers'],
  ['Overdue Ageing', 'All Ageing Buckets'],
];

const KPI_ROW_1 = [
  { label: 'Field Representatives', value: '24', note: 'Demo employee profiles', icon: Users },
  { label: 'Customer Accounts', value: '1,250', note: 'Demo geofence zones', icon: Store },
  { label: 'Visits', value: '86', note: '72 completed, 14 active', icon: CalendarDays },
  { label: 'Geo Compliance', value: '96%', note: 'Check-ins inside geofence', icon: MapPin },
];

const KPI_ROW_2 = [
  { label: 'Total Sales', value: '₹12,34,567.00', note: 'Demo consolidated billing', tone: 'dark' },
  { label: 'Total Collection', value: '₹9,87,654.00', note: 'Demo realised payments', tone: 'dark' },
  { label: 'Market Outstanding', value: '₹2,46,913.00', note: 'Demo uncollected balance', tone: 'amber' },
  { label: 'Critical (>90d overdue)', value: '₹45,678.00', note: 'Demo delinquent balance', tone: 'red' },
];

export const DashboardScreen: React.FC = () => (
  <div className="ftl-db">
    <aside className="ftl-db-side">
      <div className="ftl-db-brand">
        <span className="ftl-db-brand-mark">
          <ShieldCheck aria-hidden="true" />
        </span>
        <div>
          <b>FieldTrack Pro</b>
          <small>Admin Dashboard</small>
        </div>
      </div>
      {NAV.map(({ icon: Icon, label }, i) => (
        <div key={label} className={`ftl-db-nav${i === 0 ? ' is-active' : ''}`}>
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </div>
      ))}
      <div className="ftl-db-nav ftl-db-nav--end">
        <Settings aria-hidden="true" />
        <span>Settings</span>
      </div>
    </aside>
    <div className="ftl-db-main">
      <div className="ftl-db-top">
        <span className="ftl-db-online">
          <i /> API Online
        </span>
        <Bell aria-hidden="true" />
        <span className="ftl-db-role">Super Admin</span>
      </div>
      <h4 className="ftl-db-title">Executive Dashboard &amp; BI</h4>
      <p className="ftl-db-sub">Unified business intelligence, multi-brand analytics and the live field operations command center.</p>

      <div className="ftl-db-banner">
        <span className="ftl-db-banner-ico">
          <CalendarDays aria-hidden="true" />
        </span>
        <div>
          <b>
            Monthly Close Required <em>Action item</em>
          </b>
          <span>The previous month is ready for review and closing.</span>
        </div>
        <span className="ftl-db-btn ftl-db-btn--ghost">Review month</span>
        <span className="ftl-db-btn">
          <Lock aria-hidden="true" /> Close &amp; lock
        </span>
      </div>

      <div className="ftl-db-banner ftl-db-banner--soft">
        <span className="ftl-db-banner-ico">
          <ShieldCheck aria-hidden="true" />
        </span>
        <div>
          <b>
            Financial Source of Truth: Tally Prime <em className="is-ok">Agent standby</em>
          </b>
          <span>Company: Demo Distributors Pvt Ltd · Last sync: a few minutes ago</span>
        </div>
        <span className="ftl-db-btn ftl-db-btn--ghost">Sync health</span>
      </div>

      <div className="ftl-db-filter-head">Dashboard BI filter engine</div>
      <div className="ftl-db-filters">
        {FILTERS.map(([k, v]) => (
          <div key={k}>
            <small>{k}</small>
            <span>{v} ▾</span>
          </div>
        ))}
      </div>

      <div className="ftl-db-kpis">
        {KPI_ROW_1.map(({ label, value, note, icon: Icon }) => (
          <div key={label} className="ftl-db-kpi">
            <div className="ftl-db-kpi-head">
              <small>{label}</small>
              <span className="ftl-db-kpi-ico">
                <Icon aria-hidden="true" />
              </span>
            </div>
            <b>{value}</b>
            <span>{note}</span>
          </div>
        ))}
      </div>
      <div className="ftl-db-kpis">
        {KPI_ROW_2.map(({ label, value, note, tone }) => (
          <div key={label} className="ftl-db-kpi">
            <div className="ftl-db-kpi-head">
              <small>{label}</small>
              <span className={`ftl-db-kpi-ico is-${tone}`}>
                <IndianRupee aria-hidden="true" />
              </span>
            </div>
            <b>{value}</b>
            <span>{note}</span>
          </div>
        ))}
      </div>
    </div>
  </div>
);

const PHONE_VISITS = [
  { name: 'Outlet 0214 · Market Rd', time: '09:30', state: 'done' },
  { name: 'Outlet 0388 · Station Sq', time: '11:00', state: 'now' },
  { name: 'Outlet 0521 · Ring Rd', time: '12:45', state: 'next' },
  { name: 'Outlet 0607 · Old Bazaar', time: '14:15', state: 'next' },
];

/** Android app home screen (demo data), sized 300 x 620 CSS px. */
export const PhoneScreen: React.FC = () => (
  <div className="ftl-ph">
    <div className="ftl-ph-status">
      <span>9:41</span>
      <i className="ftl-ph-notch" />
      <span>5G</span>
    </div>
    <div className="ftl-ph-head">
      <small>Today · Rep 07</small>
      <b>4 visits planned</b>
      <div className="ftl-ph-bar">
        <span style={{ width: '38%' }} />
      </div>
    </div>
    <div className="ftl-ph-map">
      <svg viewBox="0 0 280 120" aria-hidden="true">
        <path d="M0 40H280M0 84H280M60 0V120M150 0V120M228 0V120" stroke="rgba(255,255,255,.08)" strokeWidth="6" />
        <path d="M20 100 L60 100 L60 40 L150 40 L150 84 L228 84 L228 14" fill="none" stroke="#ff9f2e" strokeWidth="3" strokeLinejoin="round" />
        <circle cx="150" cy="62" r="6" fill="#ff9f2e" />
        <circle cx="150" cy="62" r="14" fill="none" stroke="#ff9f2e" strokeOpacity=".4" strokeWidth="2" />
      </svg>
    </div>
    <div className="ftl-ph-list">
      {PHONE_VISITS.map((v) => (
        <div key={v.name} className={`ftl-ph-row is-${v.state}`}>
          <i />
          <div>
            <b>{v.name}</b>
            <small>{v.time}</small>
          </div>
          <span>{v.state === 'done' ? 'Done' : v.state === 'now' ? 'Now' : 'Next'}</span>
        </div>
      ))}
    </div>
    <div className="ftl-ph-cta">
      <MapPin aria-hidden="true" /> Check in · inside geofence 12 m
    </div>
  </div>
);

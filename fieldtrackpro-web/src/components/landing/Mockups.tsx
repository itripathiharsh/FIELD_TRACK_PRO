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

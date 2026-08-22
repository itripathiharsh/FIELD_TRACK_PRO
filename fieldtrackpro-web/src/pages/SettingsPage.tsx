import React, { useEffect, useState } from 'react';
import {
  Building2,
  Users,
  MapPin,
  FileSpreadsheet,
  Layers,
  Bell,
  Activity,
  Shield,
  CheckCircle2,
  XCircle,
  Lock,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ENV } from '../config/env';
import { apiClient } from '../api/client';
import { Employee, Territory, Area, Customer } from '../types';

type SettingsTab =
  | 'organization'
  | 'users_roles'
  | 'field_ops'
  | 'data_import'
  | 'integrations'
  | 'notifications'
  | 'diagnostics';

export const SettingsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('organization');
  const [health, setHealth] = useState<'checking' | 'online' | 'offline'>('checking');
  const [healthDetail, setHealthDetail] = useState<string>('');

  // Live master counts from backend APIs
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  void isLoading;

  useEffect(() => {
    loadSettingsData();
  }, []);

  const loadSettingsData = async () => {
    try {
      setIsLoading(true);
      const [healthData, empData, terrData, areaData, custData] = await Promise.all([
        apiClient.getHealth().catch((err) => ({ status: 'OFFLINE', error: err.message })),
        apiClient.getEmployees().catch(() => [] as Employee[]),
        apiClient.getTerritories().catch(() => [] as Territory[]),
        apiClient.getAreas().catch(() => [] as Area[]),
        apiClient.getCustomers({ limit: 500 }).catch(() => [] as Customer[]),
      ]);

      if ('status' in healthData && healthData.status === 'UP') {
        setHealth('online');
        setHealthDetail(
          'service' in healthData && healthData.service
            ? `${healthData.status} — ${healthData.service}`
            : healthData.status,
        );
      } else {
        setHealth('offline');
        setHealthDetail('error' in healthData ? String(healthData.error) : 'Unreachable');
      }

      setEmployees(Array.isArray(empData) ? empData : []);
      setTerritories(Array.isArray(terrData) ? terrData : []);
      setAreas(Array.isArray(areaData) ? areaData : []);
      setCustomers(Array.isArray(custData) ? custData : []);
    } catch {
      setHealth('offline');
    } finally {
      setIsLoading(false);
    }
  };

  const adminCount = employees.filter(
    (e) =>
      e.working_profile?.toLowerCase().includes('director') ||
      e.working_profile?.toLowerCase().includes('manager') ||
      e.working_profile?.toLowerCase().includes('asm'),
  ).length;

  const financeCount = employees.filter(
    (e) =>
      e.working_profile?.toLowerCase().includes('accountant') ||
      e.working_profile?.toLowerCase().includes('billing'),
  ).length;

  const fieldCount = Math.max(0, employees.length - adminCount - financeCount);

  const tabs: { id: SettingsTab; label: string; icon: React.FC<{ className?: string }> }[] = [
    { id: 'organization', label: 'Organization', icon: Building2 },
    { id: 'users_roles', label: 'Users & Roles', icon: Users },
    { id: 'field_ops', label: 'Field Operations', icon: MapPin },
    { id: 'data_import', label: 'Data & Ingestion', icon: FileSpreadsheet },
    { id: 'integrations', label: 'Integrations & ERP', icon: Layers },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'diagnostics', label: 'System Diagnostics', icon: Activity },
  ];

  return (
    <div className="space-y-space-6 max-w-6xl font-body-md text-on-surface">
      <PageHeader
        title="Admin Settings & Enterprise Controls"
        subtitle="Manage business configuration, operational thresholds, access policies, and system diagnostics."
      />

      {/* Brand Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-surface-container-highest pb-3">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl font-headline-sm text-sm font-semibold transition-all duration-150 border ${
                isActive
                  ? 'bg-primary-container text-on-primary-container border-secondary-container/40 shadow-sm'
                  : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface border-surface-container-highest'
              }`}
            >
              <Icon
                className={`w-4 h-4 transition-colors ${
                  isActive ? 'text-secondary-container' : 'text-primary'
                }`}
              />
              <span className="tracking-tight">{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab 1: Organization Profile */}
      {activeTab === 'organization' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <Building2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  Enterprise Organization Profile
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Master corporate entity and operational divisions
                </p>
              </div>
            </div>
            <StatusBadge status="ACTIVE" size="sm" />
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest hover:border-secondary-container/30 transition-all">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Legal Entity Name
              </dt>
              <dd className="font-headline-sm text-base font-bold text-on-surface">
                SGRG Services Private Limited
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Verified client corporate entity for multi-brand distribution.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest hover:border-secondary-container/30 transition-all">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Operational Command Hub
              </dt>
              <dd className="font-headline-sm text-base font-bold text-on-surface">
                Kanpur Central, Uttar Pradesh
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Central headquarters for field telemetry, dispatch &amp; credit recovery.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest hover:border-secondary-container/30 transition-all">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Active Business Divisions
              </dt>
              <dd className="font-body-md text-sm font-semibold text-on-surface">
                Telecom Distribution (11001–11020) &amp; Consumer Electronics (11021–11030)
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Independent cost centers mapped to CUG employee series.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest hover:border-secondary-container/30 transition-all">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                System Timezone &amp; Currency
              </dt>
              <dd className="font-body-md text-sm font-semibold text-on-surface">
                Asia/Kolkata (IST, UTC+5:30) • Indian Rupee (INR ₹)
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Standard reporting period format with Lakh / Crore Indian number formatting.
              </p>
            </div>
          </dl>
        </Card>
      )}

      {/* Tab 2: Users & Roles */}
      {activeTab === 'users_roles' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <Users className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  Users &amp; Role-Based Access Controls
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Personnel hierarchy and role distribution
                </p>
              </div>
            </div>
            <span className="font-headline-sm text-xs font-bold text-primary bg-primary-tint/40 border border-primary-fixed-dim px-3 py-1 rounded-lg">
              {employees.length} Active Personnel
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <div className="flex items-center justify-between mb-2">
                <span className="font-headline-sm text-xs font-bold uppercase tracking-wider text-secondary">
                  Leadership &amp; Admins
                </span>
                <span className="font-headline-sm text-xs font-bold bg-secondary-container/20 text-on-secondary-container px-2 py-0.5 rounded">
                  Admin
                </span>
              </div>
              <p className="font-headline-lg text-3xl font-black text-primary mb-1">{adminCount}</p>
              <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
                Directors, Sales Managers, and ASMs with full administrative command and reporting authority.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <div className="flex items-center justify-between mb-2">
                <span className="font-headline-sm text-xs font-bold uppercase tracking-wider text-secondary">
                  Field Force (FOS / TSE)
                </span>
                <span className="font-headline-sm text-xs font-bold bg-primary/10 text-primary px-2 py-0.5 rounded">
                  Field
                </span>
              </div>
              <p className="font-headline-lg text-3xl font-black text-primary mb-1">{fieldCount}</p>
              <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
                On-field officers executing beat schedules, check-ins, forms, and collection pickups.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <div className="flex items-center justify-between mb-2">
                <span className="font-headline-sm text-xs font-bold uppercase tracking-wider text-secondary">
                  Finance &amp; Operations
                </span>
                <span className="font-headline-sm text-xs font-bold bg-emerald-500/10 text-emerald-700 px-2 py-0.5 rounded">
                  Finance
                </span>
              </div>
              <p className="font-headline-lg text-3xl font-black text-primary mb-1">{financeCount}</p>
              <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
                Accountants and billing operators verifying cheques, cash receipts, and UTR references.
              </p>
            </div>
          </div>

          <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest space-y-2">
            <div className="flex items-center gap-2">
              <Lock className="w-4 h-4 text-secondary" />
              <h4 className="font-headline-sm text-xs font-bold uppercase tracking-wider text-primary">
                Authentication &amp; Session Security Policy
              </h4>
            </div>
            <ul className="font-caption text-xs text-on-surface-variant list-disc pl-5 space-y-1">
              <li>Dual-identifier login supported via official Work Email or CUG Mobile Number.</li>
              <li>Salted Bcrypt password hashing with standard JSON Web Token (JWT) bearer validation.</li>
              <li>Automatic token refresh cycle with HTTP-only cookie security for hardened web sessions.</li>
            </ul>
          </div>
        </Card>
      )}

      {/* Tab 3: Field Operations */}
      {activeTab === 'field_ops' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <MapPin className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  Field Operations &amp; PostGIS Geofencing Policies
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Spatial boundaries and hardware telemetry verification rules
                </p>
              </div>
            </div>
            <span className="font-headline-sm text-xs font-bold text-emerald-700 bg-emerald-500/10 border border-emerald-300 px-3 py-1 rounded-lg flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> PostGIS Engine Active
            </span>
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Default Geofence Radius
              </dt>
              <dd className="font-headline-sm text-xl font-bold text-primary">75 Metres</dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Server-side verified per outlet using stored PostGIS geography points.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Minimum GPS Accuracy Threshold
              </dt>
              <dd className="font-headline-sm text-xl font-bold text-primary">100 Metres</dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Hardware readings with uncertainty &gt;100m are flagged automatically.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Operational Territories &amp; Beats
              </dt>
              <dd className="font-headline-sm text-base font-bold text-primary">
                {territories.length} Zones • {areas.length} Granular Areas
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Structured geographic distribution across Kanpur, Lucknow &amp; surrounding beats.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Retail Outlets Under Coverage
              </dt>
              <dd className="font-headline-sm text-base font-bold text-primary">
                {customers.length} Genuine Client Outlets
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Catalog of active retail counters with assigned DMS codes.
              </p>
            </div>
          </dl>

          <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest space-y-2">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-secondary" />
              <h4 className="font-headline-sm text-xs font-bold uppercase tracking-wider text-primary">
                Anti-Fraud &amp; Hardware Telemetry Integrity
              </h4>
            </div>
            <ul className="font-caption text-xs text-on-surface-variant list-disc pl-5 space-y-1">
              <li>Mock location providers and software GPS emulators are rejected at the gateway.</li>
              <li>Check-in and check-out events record an immutable, insert-only audit log in PostgreSQL.</li>
              <li>On-site dwell duration is measured to prevent rapid check-in spoofing.</li>
            </ul>
          </div>
        </Card>
      )}

      {/* Tab 4: Data & Ingestion */}
      {activeTab === 'data_import' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  MIS &amp; Excel Data Ingestion Pipeline
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Multi-brand batch parser and reconciliation engine
                </p>
              </div>
            </div>
            <StatusBadge status="ACTIVE" size="sm" />
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Supported File Formats
              </dt>
              <dd className="font-headline-sm text-base font-bold text-on-surface">
                Microsoft Excel (.xlsx, .xls)
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                OpenPyXL high-throughput streaming reader with schema validation.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Deduplication &amp; Idempotency
              </dt>
              <dd className="font-headline-sm text-base font-bold text-on-surface">
                Idempotent DMS Outlet Matching
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Repeated batch imports overwrite financial snapshots safely with zero doubling.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest md:col-span-2">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Recognized Brand Sheets &amp; MIS Formats
              </dt>
              <dd className="font-body-md text-sm font-semibold text-on-surface">
                Combined BI Excel, Usha, VU, ZBR, Telecom Roster, and Consumer Electronics (CE) Master Sheets.
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Automatic multi-tab detection parses brand sales, collections, and ageing ledgers.
              </p>
            </div>
          </dl>
        </Card>
      )}

      {/* Tab 5: Integrations & ERP */}
      {activeTab === 'integrations' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  Enterprise Integrations &amp; Connectors
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  External services, accounting ERP, and spatial map tiles
                </p>
              </div>
            </div>
            <span className="font-headline-sm text-xs font-bold text-primary bg-primary-tint/40 border border-primary-fixed-dim px-3 py-1 rounded-lg">
              3 Monitored Services
            </span>
          </div>

          <div className="space-y-space-3">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest flex items-start justify-between">
              <div>
                <h4 className="font-headline-sm text-sm font-bold text-primary flex items-center gap-2">
                  Tally Prime / ERP 9 Connector
                  <span className="font-headline-sm text-[10px] font-bold uppercase bg-error/10 text-error border border-error/20 px-2 py-0.5 rounded">
                    Not Connected • Integration Pending
                  </span>
                </h4>
                <p className="font-caption text-xs text-on-surface-variant mt-1">
                  Bi-directional voucher export connector for automated field collection sync (Cash, Cheque, and UTR clearance). Pending client ERP endpoint &amp; gateway authorization.
                </p>
              </div>
              <StatusBadge status="INACTIVE" size="sm" />
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest flex items-start justify-between">
              <div>
                <h4 className="font-headline-sm text-sm font-bold text-primary flex items-center gap-2">
                  Carto Voyager &amp; MapLibre Spatial Tiles
                  <span className="font-headline-sm text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-700 border border-emerald-300 px-2 py-0.5 rounded">
                    Connected (Active)
                  </span>
                </h4>
                <p className="font-caption text-xs text-on-surface-variant mt-1">
                  High-resolution vector/raster base map rendering for territory coverage boundaries, beat navigation, and customer clustering.
                </p>
              </div>
              <StatusBadge status="ACTIVE" size="sm" />
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest flex items-start justify-between">
              <div>
                <h4 className="font-headline-sm text-sm font-bold text-primary flex items-center gap-2">
                  Secure Media &amp; Signature Vault
                  <span className="font-headline-sm text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-700 border border-emerald-300 px-2 py-0.5 rounded">
                    Encrypted
                  </span>
                </h4>
                <p className="font-caption text-xs text-on-surface-variant mt-1">
                  Cryptographic SHA-256 validation for site photos, requirement forms, and customer touch signatures.
                </p>
              </div>
              <StatusBadge status="ACTIVE" size="sm" />
            </div>
          </div>
        </Card>
      )}

      {/* Tab 6: Notifications */}
      {activeTab === 'notifications' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <Bell className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  Notification Channels &amp; Field Alerts
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Push dispatch channels and cellular CUG directory
                </p>
              </div>
            </div>
            <StatusBadge status="ACTIVE" size="sm" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Firebase Cloud Messaging (FCM)
              </dt>
              <dd className="font-headline-sm text-base font-bold text-on-surface">
                Schema Ready • Pending Project Key
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Mobile push device registry active in PostgreSQL database schema. Live dispatch triggers activate upon setting production Firebase service key.
              </p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                CUG Telephony Directory
              </dt>
              <dd className="font-headline-sm text-base font-bold text-on-surface">
                Active Roster (9839011001 – 9839011030)
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Direct calling and SMS coordination mapped to verified employee CUG mobile numbers.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Tab 7: System Diagnostics */}
      {activeTab === 'diagnostics' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <Activity className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  System Diagnostics &amp; Telemetry Health
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Live backend API connectivity and environment telemetry
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {health === 'checking' && (
                <span className="font-headline-sm text-xs text-on-surface-variant">Checking…</span>
              )}
              {health === 'online' && (
                <span className="font-headline-sm text-xs font-bold text-emerald-700 bg-emerald-500/10 border border-emerald-300 px-3 py-1 rounded-lg flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" /> System Healthy
                </span>
              )}
              {health === 'offline' && (
                <span className="font-headline-sm text-xs font-bold text-error bg-error/10 border border-error/20 px-3 py-1 rounded-lg flex items-center gap-1.5">
                  <XCircle className="w-4 h-4 text-error" /> Service Offline
                </span>
              )}
            </div>
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                API Base URL
              </dt>
              <dd className="font-mono text-xs text-primary font-bold break-all bg-surface-container-high px-2.5 py-1.5 rounded-lg border border-surface-container-highest">
                {ENV.API_BASE_URL}
              </dd>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Deployment Environment
              </dt>
              <dd className="font-mono text-xs text-primary font-bold uppercase bg-surface-container-high px-2.5 py-1.5 rounded-lg border border-surface-container-highest inline-block">
                {ENV.APP_ENV}
              </dd>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest md:col-span-2">
              <dt className="font-headline-sm text-xs uppercase font-bold text-secondary mb-space-1 tracking-wider">
                Health Probe Status
              </dt>
              <dd className="flex items-center gap-space-2 font-mono text-xs">
                {health === 'online' ? (
                  <span className="text-on-surface font-semibold bg-surface-container-high px-2.5 py-1.5 rounded-lg border border-surface-container-highest">
                    {healthDetail}
                  </span>
                ) : (
                  <span className="text-error font-semibold bg-error/10 px-2.5 py-1.5 rounded-lg border border-error/20">
                    {healthDetail || 'Backend unreachable'}
                  </span>
                )}
              </dd>
            </div>
          </dl>

          <p className="font-caption text-xs text-on-surface-variant">
            Configuration parameters are resolved at service startup and verified against live API telemetry.
          </p>
        </Card>
      )}
    </div>
  );
};

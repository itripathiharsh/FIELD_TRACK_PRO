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

      {/* Settings Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-surface-container-highest pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-headline-sm text-sm font-semibold transition-all ${
                isActive
                  ? 'bg-primary text-on-primary shadow-sm'
                  : 'bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-on-primary' : 'text-primary'}`} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Organization Profile */}
      {activeTab === 'organization' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-2">
              <Building2 className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                Enterprise Organization Profile
              </h3>
            </div>
            <StatusBadge status="ACTIVE" size="sm" />
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4 font-caption text-xs">
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Legal Entity Name
              </dt>
              <dd className="text-on-surface font-semibold text-sm">SGRG Services Private Limited</dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Operational Command Hub
              </dt>
              <dd className="text-on-surface font-semibold text-sm">Kanpur Central, Uttar Pradesh</dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Active Business Divisions
              </dt>
              <dd className="text-on-surface font-medium">
                Telecom Distribution (11001–11020) &amp; Consumer Electronics (11021–11030)
              </dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                System Timezone &amp; Currency
              </dt>
              <dd className="text-on-surface font-medium">
                Asia/Kolkata (IST, UTC+5:30) • INR (₹)
              </dd>
            </div>
          </dl>
        </Card>
      )}

      {/* Tab 2: Users & Roles */}
      {activeTab === 'users_roles' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-2">
              <Users className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                Users &amp; Role-Based Access Controls
              </h3>
            </div>
            <span className="text-xs font-semibold text-on-surface-variant bg-surface-container px-2.5 py-1 rounded">
              {employees.length} Active Personnel
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant">
              <span className="text-xs font-bold uppercase text-primary block mb-1">
                Leadership &amp; Admins
              </span>
              <p className="text-2xl font-black text-on-surface mb-1">{adminCount}</p>
              <p className="text-xs text-on-surface-variant">
                Directors &amp; Sales Managers with full administrative override &amp; reporting authority.
              </p>
            </div>
            <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant">
              <span className="text-xs font-bold uppercase text-primary block mb-1">
                Field Force (FOS / TSE)
              </span>
              <p className="text-2xl font-black text-on-surface mb-1">{fieldCount}</p>
              <p className="text-xs text-on-surface-variant">
                On-field officers executing beat visits, customer check-ins, and payment collections.
              </p>
            </div>
            <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant">
              <span className="text-xs font-bold uppercase text-primary block mb-1">
                Finance &amp; Operations
              </span>
              <p className="text-2xl font-black text-on-surface mb-1">{financeCount}</p>
              <p className="text-xs text-on-surface-variant">
                Accountants &amp; billing operators verifying cheques, cash, and online UTR receipts.
              </p>
            </div>
          </div>

          <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant space-y-2">
            <div className="flex items-center gap-2">
              <Lock className="w-4 h-4 text-primary" />
              <h4 className="font-headline-sm text-xs font-bold uppercase text-primary">
                Authentication &amp; Security Policy
              </h4>
            </div>
            <ul className="text-xs text-on-surface-variant list-disc pl-5 space-y-1">
              <li>Dual-identifier login supported via official Work Email or CUG Mobile Number.</li>
              <li>Encrypted salted Bcrypt hashing with standard JSON Web Token (JWT) bearer verification.</li>
              <li>Automatic token refresh lifecycle with hardened HTTP-only cookie support.</li>
            </ul>
          </div>
        </Card>
      )}

      {/* Tab 3: Field Operations */}
      {activeTab === 'field_ops' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-2">
              <MapPin className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                Field Operations &amp; PostGIS Geofencing Policies
              </h3>
            </div>
            <span className="text-xs font-semibold text-secondary bg-surface-container px-2.5 py-1 rounded flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-secondary" /> PostGIS Active
            </span>
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4 font-caption text-xs">
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Default Geofence Radius
              </dt>
              <dd className="text-on-surface font-semibold text-sm">75 Metres</dd>
              <p className="text-on-surface-variant mt-1 text-[11px]">
                Server-side verified per outlet from stored GPS coordinates.
              </p>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Minimum GPS Accuracy Threshold
              </dt>
              <dd className="text-on-surface font-semibold text-sm">100 Metres</dd>
              <p className="text-on-surface-variant mt-1 text-[11px]">
                Readings exceeding 100m error margin are flagged for review.
              </p>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Operational Territories &amp; Beats
              </dt>
              <dd className="text-on-surface font-semibold text-sm">
                {territories.length} Zones • {areas.length} Granular Areas
              </dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Registered Outlets Under Coverage
              </dt>
              <dd className="text-on-surface font-semibold text-sm">{customers.length} Verified Outlets</dd>
            </div>
          </dl>

          <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant space-y-2">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary" />
              <h4 className="font-headline-sm text-xs font-bold uppercase text-primary">
                Anti-Fraud &amp; Hardware Telemetry Integrity
              </h4>
            </div>
            <ul className="text-xs text-on-surface-variant list-disc pl-5 space-y-1">
              <li>Mock location signals and software GPS emulators are rejected automatically.</li>
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
            <div className="flex items-center gap-space-2">
              <FileSpreadsheet className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                MIS &amp; Excel Data Ingestion Pipeline
              </h3>
            </div>
            <StatusBadge status="ACTIVE" size="sm" />
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4 font-caption text-xs">
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Supported File Types
              </dt>
              <dd className="text-on-surface font-semibold text-sm">Microsoft Excel (.xlsx, .xls)</dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Deduplication &amp; Reconciliation Engine
              </dt>
              <dd className="text-on-surface font-semibold text-sm">Idempotent DMS Code Matching</dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant md:col-span-2">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Recognized Brand Sheets &amp; Formats
              </dt>
              <dd className="text-on-surface font-medium">
                Combined BI Excel, Usha, VU, ZBR, Telecom Roster, and Consumer Electronics (CE) Master Sheets.
              </dd>
            </div>
          </dl>
        </Card>
      )}

      {/* Tab 5: Integrations & ERP */}
      {activeTab === 'integrations' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-2">
              <Layers className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                Enterprise Integrations &amp; Connectors
              </h3>
            </div>
            <span className="text-xs font-semibold text-on-surface-variant bg-surface-container px-2.5 py-1 rounded">
              3 Connected Services
            </span>
          </div>

          <div className="space-y-space-3">
            <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant flex items-start justify-between">
              <div>
                <h4 className="font-headline-sm text-sm font-bold text-on-surface flex items-center gap-2">
                  Tally Prime / ERP 9 Connector
                  <span className="text-[10px] font-bold uppercase bg-error/10 text-error px-2 py-0.5 rounded">
                    Not Connected • Integration Pending
                  </span>
                </h4>
                <p className="text-xs text-on-surface-variant mt-1">
                  Bi-directional voucher export connector for automated field collection sync. Pending client ERP endpoint &amp; gateway authorization.
                </p>
              </div>
              <StatusBadge status="INACTIVE" size="sm" />
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant flex items-start justify-between">
              <div>
                <h4 className="font-headline-sm text-sm font-bold text-on-surface flex items-center gap-2">
                  Carto Voyager &amp; MapLibre Spatial Tiles
                  <span className="text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500 px-2 py-0.5 rounded">
                    Connected (Active)
                  </span>
                </h4>
                <p className="text-xs text-on-surface-variant mt-1">
                  High-resolution vector/raster base map rendering for territory coverage boundaries and customer clustering.
                </p>
              </div>
              <StatusBadge status="ACTIVE" size="sm" />
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-lg border border-outline-variant flex items-start justify-between">
              <div>
                <h4 className="font-headline-sm text-sm font-bold text-on-surface flex items-center gap-2">
                  Secure Media &amp; Signature Vault
                  <span className="text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-500 px-2 py-0.5 rounded">
                    Encrypted
                  </span>
                </h4>
                <p className="text-xs text-on-surface-variant mt-1">
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
            <div className="flex items-center gap-space-2">
              <Bell className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                Notification Channels &amp; Field Alerts
              </h3>
            </div>
            <StatusBadge status="ACTIVE" size="sm" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4 font-caption text-xs">
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Firebase Cloud Messaging (FCM)
              </dt>
              <dd className="text-on-surface font-semibold text-sm">Schema Ready • Pending Project Key</dd>
              <p className="text-on-surface-variant mt-1 text-[11px]">
                Mobile push device registry active in database schema. Live dispatch triggers activate upon setting production Firebase service key.
              </p>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                CUG Telephony Directory
              </dt>
              <dd className="text-on-surface font-semibold text-sm">Active Roster (9839011001 – 9839011030)</dd>
              <p className="text-on-surface-variant mt-1 text-[11px]">
                Direct calling &amp; SMS coordination mapped to verified employee CUG mobile numbers.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Tab 7: System Diagnostics */}
      {activeTab === 'diagnostics' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3">
            <div className="flex items-center gap-space-2">
              <Activity className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">
                System Diagnostics &amp; Telemetry Health
              </h3>
            </div>
            <div className="flex items-center gap-2">
              {health === 'checking' && (
                <span className="text-xs text-on-surface-variant">Checking…</span>
              )}
              {health === 'online' && (
                <span className="text-xs font-semibold text-secondary flex items-center gap-1">
                  <CheckCircle2 className="w-4 h-4 text-secondary" /> System Healthy
                </span>
              )}
              {health === 'offline' && (
                <span className="text-xs font-semibold text-error flex items-center gap-1">
                  <XCircle className="w-4 h-4 text-error" /> Service Offline
                </span>
              )}
            </div>
          </div>

          <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4 font-caption text-xs">
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                API Base URL
              </dt>
              <dd className="text-primary font-mono break-all text-xs">{ENV.API_BASE_URL}</dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Deployment Environment
              </dt>
              <dd className="text-primary font-mono text-xs uppercase">{ENV.APP_ENV}</dd>
            </div>
            <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant md:col-span-2">
              <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
                Health Check Endpoint Status
              </dt>
              <dd className="flex items-center gap-space-2 font-mono text-xs">
                {health === 'online' ? (
                  <span className="text-on-surface">{healthDetail}</span>
                ) : (
                  <span className="text-error">{healthDetail || 'Backend unreachable'}</span>
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

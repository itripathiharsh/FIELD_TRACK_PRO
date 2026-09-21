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
  Tag,
  Plus,
  Loader2,
  RefreshCw,
  ArrowDownLeft,
  ArrowUpRight,
  AlertTriangle,
  Clock,
  Database,
  Info,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { StatusBadge } from '../components/ui/StatusBadge';
import { AddBrandModal } from '../components/ui/AddBrandModal';
import { Modal } from '../components/ui/Modal';
import { ENV } from '../config/env';
import { apiClient } from '../api/client';
import {
  Employee,
  Territory,
  Area,
  OrganizationProfile,
  Brand,
  TallyIntegrationStatus,
  TallyAuditLogItem,
} from '../types';

type SettingsTab =
  | 'organization'
  | 'brands'
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

  // Live master counts, brands, and organization profile from backend APIs
  const [orgProfile, setOrgProfile] = useState<OrganizationProfile | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [customerTotal, setCustomerTotal] = useState(0);
  const [tallyStatus, setTallyStatus] = useState<TallyIntegrationStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAddBrandOpen, setIsAddBrandOpen] = useState(false);
  const [updatingBrandId, setUpdatingBrandId] = useState<string | null>(null);

  // Tally Audit Logs & Monitoring State
  const [auditLogs, setAuditLogs] = useState<TallyAuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditSkip, setAuditSkip] = useState(0);
  const auditLimit = 15;
  const [isAuditLoading, setIsAuditLoading] = useState(false);
  const [filterDirection, setFilterDirection] = useState<'ALL' | 'READ' | 'WRITE'>('ALL');
  const [filterStatus, setFilterStatus] = useState<'ALL' | 'SUCCESS' | 'FAILED'>('ALL');
  const [filterEntity, setFilterEntity] = useState<'ALL' | 'CUSTOMERS' | 'INVOICES' | 'PAYMENTS'>('ALL');
  const [selectedAuditLog, setSelectedAuditLog] = useState<TallyAuditLogItem | null>(null);

  useEffect(() => {
    loadSettingsData();
  }, []);

  const loadAuditLogs = async (newSkip = auditSkip) => {
    try {
      setIsAuditLoading(true);
      const res = await apiClient.getTallyAuditLogs({
        direction: filterDirection !== 'ALL' ? filterDirection : undefined,
        status: filterStatus !== 'ALL' ? filterStatus : undefined,
        entity_type: filterEntity !== 'ALL' ? filterEntity : undefined,
        skip: newSkip,
        limit: auditLimit,
      });
      setAuditLogs(res.items || []);
      setAuditTotal(res.total || 0);
      setAuditSkip(newSkip);
    } catch {
      // Handled gracefully
    } finally {
      setIsAuditLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'integrations') {
      loadAuditLogs(0);
    }
  }, [activeTab, filterDirection, filterStatus, filterEntity]);

  const loadSettingsData = async () => {
    try {
      setIsLoading(true);
      const [healthData, orgData, empData, terrData, areaData, custPaginated, brandsData, tallyData] = await Promise.all([
        apiClient.getHealth().catch((err) => ({ status: 'OFFLINE', error: err.message })),
        apiClient.getOrganizationProfile().catch(() => null),
        apiClient.getEmployees().catch(() => [] as Employee[]),
        apiClient.getTerritories().catch(() => [] as Territory[]),
        apiClient.getAreas().catch(() => [] as Area[]),
        apiClient.getCustomersPaginated({ skip: 0, limit: 1 }).catch(() => ({ items: [], total: 0 })),
        apiClient.getBrands(false).catch(() => [] as Brand[]),
        apiClient.getTallyStatus().catch(() => null),
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

      setOrgProfile(orgData);
      setEmployees(Array.isArray(empData) ? empData : []);
      setTerritories(Array.isArray(terrData) ? terrData : []);
      setAreas(Array.isArray(areaData) ? areaData : []);
      setCustomerTotal(custPaginated?.total || orgData?.total_customers || 0);
      setBrands(Array.isArray(brandsData) ? brandsData : []);
      setTallyStatus(tallyData);
    } catch {
      setHealth('offline');
      setHealthDetail('Configuration load error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleBrandStatus = async (brand: Brand) => {
    try {
      setUpdatingBrandId(brand.id);
      const updated = await apiClient.updateBrand(brand.id, { is_active: !brand.is_active });
      setBrands((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
    } catch {
      // Ignored
    } finally {
      setUpdatingBrandId(null);
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
    { id: 'brands', label: 'Brand Management', icon: Tag },
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
        actions={
          <button
            onClick={loadSettingsData}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-surface-container-highest text-xs font-semibold hover:bg-surface-container transition-colors disabled:opacity-50 text-on-surface"
          >
            <Activity className={`w-3.5 h-3.5 text-primary ${isLoading ? 'animate-spin' : ''}`} />
            {isLoading ? 'Loading...' : 'Refresh'}
          </button>
        }
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
                {orgProfile?.organization_name || 'Organization Profile Loading...'}
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
                {orgProfile?.operational_hub || 'Kanpur Central, Uttar Pradesh'}
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
                {orgProfile?.divisions || 'Telecom Distribution & Consumer Electronics'}
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
                {orgProfile?.timezone || 'Asia/Kolkata (IST, UTC+5:30)'} • {orgProfile?.currency || 'Indian Rupee (INR ₹)'}
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Standard reporting period format with Lakh / Crore Indian number formatting.
              </p>
            </div>
          </dl>
        </Card>
      )}

      {/* Tab: Brand Management */}
      {activeTab === 'brands' && (
        <Card variant="default" className="space-y-space-5">
          <div className="flex items-center justify-between border-b border-surface-container-highest pb-space-3 flex-wrap gap-3">
            <div className="flex items-center gap-space-3">
              <div className="p-2 rounded-lg bg-primary-container/10 text-primary">
                <Tag className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-headline-sm text-lg font-bold text-primary tracking-tight">
                  Brand Management &amp; Catalog
                </h3>
                <p className="font-caption text-xs text-on-surface-variant">
                  Central source of truth for brands across Customer Onboarding, Payments, and Requirements
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsAddBrandOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-primary text-on-primary hover:bg-primary/90 transition-all shadow-sm"
            >
              <Plus className="w-4 h-4" />
              <span>+ Add New Brand</span>
            </button>
          </div>

          {/* Quick Metrics */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-4">
            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <span className="font-headline-sm text-xs font-bold uppercase tracking-wider text-secondary">
                Total Master Brands
              </span>
              <p className="font-headline-lg text-3xl font-black text-primary mt-1">{brands.length}</p>
              <p className="font-caption text-xs text-on-surface-variant mt-0.5">Configured in central database</p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <span className="font-headline-sm text-xs font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                Active Brands
              </span>
              <p className="font-headline-lg text-3xl font-black text-emerald-600 dark:text-emerald-400 mt-1">
                {brands.filter((b) => b.is_active).length}
              </p>
              <p className="font-caption text-xs text-on-surface-variant mt-0.5">Selectable across FieldTrack</p>
            </div>

            <div className="p-space-4 bg-surface-container-low rounded-xl border border-surface-container-highest">
              <span className="font-headline-sm text-xs font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                Archived / Inactive
              </span>
              <p className="font-headline-lg text-3xl font-black text-amber-600 dark:text-amber-400 mt-1">
                {brands.filter((b) => !b.is_active).length}
              </p>
              <p className="font-caption text-xs text-on-surface-variant mt-0.5">Hidden from new dropdowns</p>
            </div>
          </div>

          {/* Brands List Table */}
          <div className="overflow-x-auto rounded-xl border border-surface-container-highest">
            <table className="w-full text-left text-xs text-on-surface">
              <thead className="bg-surface-container text-on-surface-variant font-bold uppercase tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-4 py-3">Brand Name</th>
                  <th className="px-4 py-3">Normalized Identifier</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest bg-surface">
                {brands.map((brand) => (
                  <tr key={brand.id} className="hover:bg-surface-container-low transition-colors">
                    <td className="px-4 py-3.5 font-bold text-on-surface flex items-center gap-2">
                      <Tag className="w-3.5 h-3.5 text-secondary" />
                      <span>{brand.name}</span>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-on-surface-variant">
                      {brand.normalized_name}
                    </td>
                    <td className="px-4 py-3.5">
                      {brand.is_active ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/10 text-amber-600 border border-amber-500/20">
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-on-surface-variant">
                      {brand.created_at ? new Date(brand.created_at).toLocaleDateString() : 'System Seed'}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        type="button"
                        onClick={() => handleToggleBrandStatus(brand)}
                        disabled={updatingBrandId === brand.id}
                        className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-all ${
                          brand.is_active
                            ? 'border-amber-500/30 text-amber-600 hover:bg-amber-500/10'
                            : 'border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10'
                        } disabled:opacity-50`}
                      >
                        {updatingBrandId === brand.id ? (
                          <Loader2 className="w-3 h-3 animate-spin inline mr-1" />
                        ) : null}
                        {brand.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}

                {brands.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-on-surface-variant italic">
                      No brands found. Click &quot;+ Add New Brand&quot; to create your first brand.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
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
                {customerTotal} Genuine Client Outlets
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
                Combined BI Excel, USHA, VU, Zebronics (ZBR alias), Telecom Roster, and Consumer Electronics (CE) Master Sheets.
              </dd>
              <p className="font-caption text-xs text-on-surface-variant mt-1">
                Automatic multi-tab detection parses brand sales, collections, and ageing ledgers with alias canonicalization.
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
            {/* Tally Prime Connector & Audit Center */}
            <div className="p-space-5 bg-surface-container-low rounded-2xl border border-surface-container-highest space-y-5">
              {/* Header & Connection Identity */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-surface-container-highest pb-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-xl bg-primary-container/10 text-primary">
                      <Database className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                        Tally Prime Accounting ERP Connector
                        {tallyStatus?.is_connected || tallyStatus?.agent_status === 'ONLINE' ? (
                          <span className="font-headline-sm text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-700 border border-emerald-300 px-2 py-0.5 rounded-full flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            Connected • Live Agent
                          </span>
                        ) : (
                          <span className="font-headline-sm text-[10px] font-bold uppercase bg-amber-500/10 text-amber-700 border border-amber-300 px-2 py-0.5 rounded-full flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                            Sync Agent Standby / Offline
                          </span>
                        )}
                      </h4>
                      <p className="font-caption text-xs text-on-surface-variant">
                        Authoritative financial accounting bridge. Active company:{' '}
                        <span className="font-semibold text-primary">
                          {tallyStatus?.tally_company_name || 'SGRG SERVICES (OPC) PRIVATE LIMITED'}
                        </span>
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3 text-xs text-on-surface-variant">
                  <div className="px-3 py-1.5 rounded-lg bg-surface-container border border-surface-container-highest flex items-center gap-2">
                    <Activity className="w-3.5 h-3.5 text-primary" />
                    <span>Agent: <strong className="text-primary">{tallyStatus?.agent_name || 'SGRG-Tally-Sync-Agent'}</strong> (v{tallyStatus?.agent_version || '1.0.0'})</span>
                  </div>
                  <div className="px-3 py-1.5 rounded-lg bg-surface-container border border-surface-container-highest flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-primary" />
                    <span>Last Heartbeat: <strong className="text-primary">{tallyStatus?.last_heartbeat_at ? new Date(tallyStatus.last_heartbeat_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'Waiting'}</strong></span>
                  </div>
                </div>
              </div>

              {/* Today's Operational Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-3.5 bg-surface rounded-xl border border-surface-container-highest space-y-1">
                  <span className="font-caption text-[11px] uppercase font-bold text-on-surface-variant tracking-wider flex items-center gap-1.5">
                    <ArrowDownLeft className="w-3.5 h-3.5 text-sky-600" />
                    Today's Reads
                  </span>
                  <div className="font-headline-sm text-xl font-bold text-primary">
                    {(tallyStatus?.today_read_count || 0).toLocaleString('en-IN')}
                  </div>
                  <p className="font-caption text-[10px] text-on-surface-variant">
                    Vouchers &amp; ledgers pulled
                  </p>
                </div>

                <div className="p-3.5 bg-surface rounded-xl border border-surface-container-highest space-y-1">
                  <span className="font-caption text-[11px] uppercase font-bold text-on-surface-variant tracking-wider flex items-center gap-1.5">
                    <ArrowUpRight className="w-3.5 h-3.5 text-purple-600" />
                    Today's Writes
                  </span>
                  <div className="font-headline-sm text-xl font-bold text-primary">
                    {(tallyStatus?.today_write_count || 0).toLocaleString('en-IN')}
                  </div>
                  <p className="font-caption text-[10px] text-on-surface-variant">
                    Receipt vouchers written back
                  </p>
                </div>

                <div className="p-3.5 bg-surface rounded-xl border border-surface-container-highest space-y-1">
                  <span className="font-caption text-[11px] uppercase font-bold text-on-surface-variant tracking-wider flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />
                    Failed Operations
                  </span>
                  <div className={`font-headline-sm text-xl font-bold ${
                    (tallyStatus?.failed_operation_count || 0) > 0 ? 'text-rose-600' : 'text-emerald-700'
                  }`}>
                    {(tallyStatus?.failed_operation_count || 0).toLocaleString('en-IN')}
                  </div>
                  <p className="font-caption text-[10px] text-on-surface-variant">
                    {(tallyStatus?.failed_operation_count || 0) > 0 ? 'Attention required' : 'Zero failures today'}
                  </p>
                </div>

                <div className="p-3.5 bg-surface rounded-xl border border-surface-container-highest space-y-1">
                  <span className="font-caption text-[11px] uppercase font-bold text-on-surface-variant tracking-wider flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    Last Successful Sync
                  </span>
                  <div className="font-headline-sm text-xs font-bold text-primary truncate">
                    {tallyStatus?.last_successful_sync_at || tallyStatus?.last_sync_at ? (
                      new Date(tallyStatus.last_successful_sync_at || tallyStatus.last_sync_at!).toLocaleString('en-IN', {
                        day: '2-digit',
                        month: 'short',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    ) : (
                      'In Progress'
                    )}
                  </div>
                  <p className="font-caption text-[10px] text-on-surface-variant">
                    {(tallyStatus?.total_invoices_synced || 0).toLocaleString('en-IN')} Invoices • {(tallyStatus?.total_payments_synced || 0).toLocaleString('en-IN')} Payments
                  </p>
                </div>
              </div>

              {/* Chronological Activity & Audit Log */}
              <div className="space-y-3 pt-2">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <h5 className="font-headline-sm text-sm font-bold text-primary flex items-center gap-2">
                      Chronological Tally Activity &amp; Audit Log
                      <span className="font-caption text-[11px] font-semibold text-on-surface-variant bg-surface-container px-2 py-0.5 rounded-full">
                        {auditTotal} logged events
                      </span>
                    </h5>
                    <p className="font-caption text-xs text-on-surface-variant">
                      Persistent, tamper-evident audit record of every Tally READ batch and WRITE outbox operation.
                    </p>
                  </div>

                  {/* Audit Filter Controls */}
                  <div className="flex flex-wrap items-center gap-2">
                    {/* Direction Filter */}
                    <div className="inline-flex rounded-lg bg-surface border border-surface-container-highest p-0.5 text-xs">
                      {(['ALL', 'READ', 'WRITE'] as const).map((dir) => (
                        <button
                          key={dir}
                          onClick={() => setFilterDirection(dir)}
                          className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                            filterDirection === dir
                              ? 'bg-primary-container text-on-primary-container shadow-xs'
                              : 'text-on-surface-variant hover:text-on-surface'
                          }`}
                        >
                          {dir === 'ALL' ? 'All Ops' : dir}
                        </button>
                      ))}
                    </div>

                    {/* Status Filter */}
                    <div className="inline-flex rounded-lg bg-surface border border-surface-container-highest p-0.5 text-xs">
                      {(['ALL', 'SUCCESS', 'FAILED'] as const).map((st) => (
                        <button
                          key={st}
                          onClick={() => setFilterStatus(st)}
                          className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                            filterStatus === st
                              ? 'bg-primary-container text-on-primary-container shadow-xs'
                              : 'text-on-surface-variant hover:text-on-surface'
                          }`}
                        >
                          {st === 'ALL' ? 'All Status' : st === 'SUCCESS' ? 'Success' : 'Failed'}
                        </button>
                      ))}
                    </div>

                    {/* Entity Filter */}
                    <select
                      value={filterEntity}
                      onChange={(e) => setFilterEntity(e.target.value as any)}
                      className="bg-surface border border-surface-container-highest text-xs rounded-lg px-2.5 py-1.5 text-on-surface focus:outline-none focus:ring-1 focus:ring-primary font-medium"
                    >
                      <option value="ALL">All Entities</option>
                      <option value="CUSTOMERS">Customers</option>
                      <option value="INVOICES">Invoices</option>
                      <option value="PAYMENTS">Payments</option>
                    </select>

                    <button
                      onClick={() => loadAuditLogs(0)}
                      disabled={isAuditLoading}
                      className="p-1.5 rounded-lg border border-surface-container-highest hover:bg-surface-container transition-colors text-on-surface-variant hover:text-primary disabled:opacity-50"
                      title="Refresh Audit Logs"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isAuditLoading ? 'animate-spin text-primary' : ''}`} />
                    </button>
                  </div>
                </div>

                {/* Audit Table */}
                <div className="overflow-x-auto rounded-xl border border-surface-container-highest bg-surface shadow-xs">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-surface-container-low border-b border-surface-container-highest text-[11px] uppercase tracking-wider text-secondary font-bold">
                      <tr>
                        <th className="py-2.5 px-3">Timestamp</th>
                        <th className="py-2.5 px-3">Type</th>
                        <th className="py-2.5 px-3">Operation / Entity</th>
                        <th className="py-2.5 px-3">Records</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3">Duration</th>
                        <th className="py-2.5 px-3">Tally Identifiers</th>
                        <th className="py-2.5 px-3 text-right">Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-container-highest/60 font-body-sm text-on-surface">
                      {isAuditLoading && auditLogs.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="py-8 text-center text-on-surface-variant">
                            <div className="flex items-center justify-center gap-2">
                              <Loader2 className="w-4 h-4 animate-spin text-primary" />
                              <span>Loading chronological audit entries...</span>
                            </div>
                          </td>
                        </tr>
                      ) : auditLogs.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="py-8 text-center text-on-surface-variant">
                            <div className="space-y-1">
                              <Info className="w-6 h-6 mx-auto text-outline" />
                              <p className="font-semibold text-xs">No matching Tally audit operations found</p>
                              <p className="font-caption text-[11px]">Adjust filters or initiate a sync cycle with the local Sync Agent.</p>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        auditLogs.map((log) => {
                          const isRead = log.direction === 'READ';
                          const isSuccess = log.status === 'SUCCESS';
                          const isFailed = log.status === 'FAILED';
                          const isPartial = log.status === 'PARTIAL';

                          return (
                            <tr key={log.id} className="hover:bg-surface-container-low/60 transition-colors">
                              <td className="py-2.5 px-3 whitespace-nowrap text-on-surface-variant text-[11px] font-mono">
                                {new Date(log.timestamp).toLocaleString('en-IN', {
                                  day: '2-digit',
                                  month: 'short',
                                  hour: '2-digit',
                                  minute: '2-digit',
                                  second: '2-digit',
                                })}
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap">
                                <span
                                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                    isRead
                                      ? 'bg-sky-500/10 text-sky-700 border border-sky-300'
                                      : 'bg-purple-500/10 text-purple-700 border border-purple-300'
                                  }`}
                                >
                                  {isRead ? (
                                    <ArrowDownLeft className="w-2.5 h-2.5" />
                                  ) : (
                                    <ArrowUpRight className="w-2.5 h-2.5" />
                                  )}
                                  {log.direction}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap">
                                <div className="font-semibold text-primary">{log.operation}</div>
                                <div className="text-[10px] text-on-surface-variant uppercase tracking-wider">{log.entity_type}</div>
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap font-medium">
                                {log.record_count.toLocaleString('en-IN')}{' '}
                                <span className="text-[10px] text-on-surface-variant">
                                  {log.record_count === 1 ? 'item' : 'items'}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap">
                                <span
                                  className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase ${
                                    isSuccess
                                      ? 'bg-emerald-500/10 text-emerald-700 border border-emerald-300'
                                      : isFailed
                                      ? 'bg-rose-500/10 text-rose-700 border border-rose-300'
                                      : isPartial
                                      ? 'bg-amber-500/10 text-amber-700 border border-amber-300'
                                      : 'bg-blue-500/10 text-blue-700 border border-blue-300'
                                  }`}
                                >
                                  {log.status}
                                </span>
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap font-mono text-[11px] text-on-surface-variant">
                                {log.duration_ms !== null && log.duration_ms !== undefined
                                  ? log.duration_ms >= 1000
                                    ? `${(log.duration_ms / 1000).toFixed(2)}s`
                                    : `${log.duration_ms}ms`
                                  : '—'}
                              </td>
                              <td className="py-2.5 px-3 text-[11px] text-on-surface-variant max-w-[200px] truncate">
                                {log.tally_voucher_number ? (
                                  <span className="font-semibold text-primary">Vch: {log.tally_voucher_number}</span>
                                ) : log.tally_guid ? (
                                  <span className="font-mono text-[10px]">GUID: {log.tally_guid.slice(0, 16)}...</span>
                                ) : log.error_message ? (
                                  <span className="text-rose-600 truncate block" title={log.error_message}>
                                    {log.error_message}
                                  </span>
                                ) : log.details?.batch_id ? (
                                  <span className="font-mono text-[10px]">Batch: {String(log.details.batch_id).slice(0, 8)}</span>
                                ) : (
                                  '—'
                                )}
                              </td>
                              <td className="py-2.5 px-3 whitespace-nowrap text-right">
                                <button
                                  onClick={() => setSelectedAuditLog(log)}
                                  className="text-[11px] font-semibold text-primary hover:text-secondary hover:underline px-2 py-1 rounded bg-surface-container hover:bg-surface-container-high transition-colors"
                                >
                                  Inspect
                                </button>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Pagination Controls */}
                {auditTotal > auditLimit && (
                  <div className="flex items-center justify-between text-xs text-on-surface-variant pt-1 px-1">
                    <span>
                      Showing <strong>{auditSkip + 1}</strong> to{' '}
                      <strong>{Math.min(auditSkip + auditLimit, auditTotal)}</strong> of{' '}
                      <strong>{auditTotal}</strong> audit records
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => loadAuditLogs(Math.max(0, auditSkip - auditLimit))}
                        disabled={auditSkip === 0 || isAuditLoading}
                        className="px-2.5 py-1 rounded-lg border border-surface-container-highest hover:bg-surface-container disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 font-semibold"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" /> Previous
                      </button>
                      <button
                        onClick={() => loadAuditLogs(auditSkip + auditLimit)}
                        disabled={auditSkip + auditLimit >= auditTotal || isAuditLoading}
                        className="px-2.5 py-1 rounded-lg border border-surface-container-highest hover:bg-surface-container disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 font-semibold"
                      >
                        Next <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Audit Log Inspect Modal */}
            {selectedAuditLog && (
              <Modal
                isOpen={!!selectedAuditLog}
                onClose={() => setSelectedAuditLog(null)}
                title={`Tally Audit Entry — ${selectedAuditLog.operation}`}
                subtitle={`Recorded on ${new Date(selectedAuditLog.timestamp).toLocaleString('en-IN')}`}
                size="lg"
              >
                <div className="space-y-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-surface-container-low p-3.5 rounded-xl border border-surface-container-highest text-xs">
                    <div>
                      <dt className="text-[10px] uppercase font-bold text-secondary">Direction</dt>
                      <dd className="font-semibold text-primary mt-0.5">{selectedAuditLog.direction}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase font-bold text-secondary">Entity Type</dt>
                      <dd className="font-semibold text-primary mt-0.5">{selectedAuditLog.entity_type}</dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase font-bold text-secondary">Status</dt>
                      <dd className="font-semibold mt-0.5">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            selectedAuditLog.status === 'SUCCESS'
                              ? 'bg-emerald-500/10 text-emerald-700'
                              : 'bg-rose-500/10 text-rose-700'
                          }`}
                        >
                          {selectedAuditLog.status}
                        </span>
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[10px] uppercase font-bold text-secondary">Duration</dt>
                      <dd className="font-mono text-primary mt-0.5">
                        {selectedAuditLog.duration_ms !== null && selectedAuditLog.duration_ms !== undefined
                          ? `${selectedAuditLog.duration_ms} ms`
                          : '—'}
                      </dd>
                    </div>
                  </div>

                  {selectedAuditLog.error_message && (
                    <div className="p-3 bg-rose-500/10 border border-rose-300 rounded-xl text-xs space-y-1">
                      <div className="flex items-center gap-1.5 font-bold text-rose-700">
                        <AlertTriangle className="w-4 h-4" />
                        Execution Error Detail
                      </div>
                      <p className="font-mono text-rose-800 text-[11px] whitespace-pre-wrap">
                        {selectedAuditLog.error_message}
                      </p>
                    </div>
                  )}

                  <div className="space-y-2">
                    <h5 className="font-headline-sm text-xs font-bold uppercase tracking-wider text-secondary">
                      Tally Identifiers &amp; Metadata
                    </h5>
                    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs bg-surface-container-low p-3 rounded-xl border border-surface-container-highest">
                      {selectedAuditLog.company_name && (
                        <div>
                          <dt className="text-on-surface-variant font-medium">Tally Company</dt>
                          <dd className="font-semibold text-primary">{selectedAuditLog.company_name}</dd>
                        </div>
                      )}
                      {selectedAuditLog.company_guid && (
                        <div>
                          <dt className="text-on-surface-variant font-medium">Company GUID</dt>
                          <dd className="font-mono text-[11px] text-primary">{selectedAuditLog.company_guid}</dd>
                        </div>
                      )}
                      {selectedAuditLog.tally_voucher_number && (
                        <div>
                          <dt className="text-on-surface-variant font-medium">Voucher Number</dt>
                          <dd className="font-semibold text-primary">{selectedAuditLog.tally_voucher_number}</dd>
                        </div>
                      )}
                      {selectedAuditLog.tally_guid && (
                        <div>
                          <dt className="text-on-surface-variant font-medium">Tally Voucher GUID</dt>
                          <dd className="font-mono text-[11px] text-primary">{selectedAuditLog.tally_guid}</dd>
                        </div>
                      )}
                    </dl>
                  </div>

                  {selectedAuditLog.details && Object.keys(selectedAuditLog.details).length > 0 && (
                    <div className="space-y-2">
                      <h5 className="font-headline-sm text-xs font-bold uppercase tracking-wider text-secondary">
                        Raw Execution Payload &amp; Batch Metrics
                      </h5>
                      <pre className="p-3 bg-surface-container rounded-xl border border-surface-container-highest text-[11px] font-mono text-on-surface overflow-x-auto max-h-60">
                        {JSON.stringify(selectedAuditLog.details, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </Modal>
            )}


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

      {/* Add Brand Modal */}
      <AddBrandModal
        isOpen={isAddBrandOpen}
        onClose={() => setIsAddBrandOpen(false)}
        onBrandCreated={(newBrand) => {
          setBrands((prev) => {
            if (prev.some((b) => b.id === newBrand.id || b.normalized_name === newBrand.normalized_name)) return prev;
            return [...prev, newBrand].sort((a, b) => a.name.localeCompare(b.name));
          });
        }}
      />
    </div>
  );
};

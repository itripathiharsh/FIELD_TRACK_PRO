import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Building2,
  CalendarCheck,
  ShieldCheck,
  AlertOctagon,
  ArrowUpRight,
  Plus,
  RefreshCw,
  TrendingUp,
  DollarSign,
  AlertTriangle,
  FileSpreadsheet,
  Download,
  Filter,
  CheckCircle2,
  Clock,
  Check,
  X,
  ChevronRight,
  Eye,
} from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import {
  Customer,
  Employee,
  Visit,
  MonthlyReportingPeriod,
  Territory,
  Area,
  DashboardSummaryResponse,
  FieldException,
  BusinessSummaryRow,
} from '../types';
import { generatePDFContent } from '../utils/pdf-report';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, isLoading: isAuthLoading } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  // Master & Filter States
  const [selectedMonth, setSelectedMonth] = useState<string>('ALL');
  const [selectedBrand, setSelectedBrand] = useState<string>('ALL');
  const [selectedZoneId, setSelectedZoneId] = useState<string>('ALL');
  const [selectedAreaId, setSelectedAreaId] = useState<string>('ALL');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('ALL');
  const [selectedAgeingBucket, setSelectedAgeingBucket] = useState<string>('ALL');

  // Reference filter options
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [employeeOptions, setEmployeeOptions] = useState<Employee[]>([]);
  const [monthlyPeriods, setMonthlyPeriods] = useState<MonthlyReportingPeriod[]>([]);

  // Core Data States
  const [visits, setVisits] = useState<Visit[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [dashboardBI, setDashboardBI] = useState<DashboardSummaryResponse | null>(null);
  const [exceptions, setExceptions] = useState<FieldException[]>([]);

  // Drilldown Modal State
  const [drilldownRow, setDrilldownRow] = useState<BusinessSummaryRow | null>(null);

  // Status & Action States
  const [isLoading, setIsLoading] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Load reference master lists for filtering
  useEffect(() => {
    if (!isAdmin) return;
    Promise.all([
      apiClient.getTerritories().catch(() => [] as Territory[]),
      apiClient.getAreas().catch(() => [] as Area[]),
      apiClient.getEmployees().catch(() => [] as Employee[]),
      apiClient.getMonthlyPeriods().catch(() => [] as MonthlyReportingPeriod[]),
    ]).then(([tList, aList, eList, pList]) => {
      setTerritories(tList || []);
      setAreas(aList || []);
      setEmployeeOptions(eList || []);
      setMonthlyPeriods(pList || []);
    });
  }, [isAdmin]);

  const availableAreas = useMemo(() => {
    if (selectedZoneId === 'ALL') return areas;
    return areas.filter((a) => a.territory_id === selectedZoneId);
  }, [areas, selectedZoneId]);

  const fetchData = useCallback(() => {
    if (isAuthLoading || !user) return;

    setIsLoading(true);
    setError(null);

    const brandParam = selectedBrand !== 'ALL' ? selectedBrand : undefined;
    const zoneParam = selectedZoneId !== 'ALL' ? selectedZoneId : undefined;
    const areaParam = selectedAreaId !== 'ALL' ? selectedAreaId : undefined;
    const employeeParam = selectedEmployeeId !== 'ALL' ? selectedEmployeeId : undefined;
    const ageingParam = selectedAgeingBucket !== 'ALL' ? selectedAgeingBucket : undefined;
    const monthParam = selectedMonth !== 'ALL' ? selectedMonth : undefined;

    const visitsPromise = isAdmin ? apiClient.getVisits() : apiClient.getMyTodayVisits();
    const customersPromise = apiClient.getCustomers().catch(() => [] as Customer[]);
    const employeesPromise = isAdmin
      ? apiClient.getEmployees().catch(() => [] as Employee[])
      : Promise.resolve([] as Employee[]);

    const biPromise = isAdmin
      ? apiClient
          .getDashboardSummary({
            brand: brandParam,
            zone_id: zoneParam,
            area_id: areaParam,
            employee_id: employeeParam,
            ageing_bucket: ageingParam,
            month: monthParam,
          })
          .catch(() => null)
      : Promise.resolve(null);

    const exceptionsPromise = isAdmin
      ? apiClient.getFieldExceptions({ limit: 10 }).catch(() => [] as FieldException[])
      : Promise.resolve([] as FieldException[]);

    Promise.all([visitsPromise, customersPromise, employeesPromise, biPromise, exceptionsPromise])
      .then(([vList, cList, eList, biData, excList]) => {
        setVisits(vList || []);
        setCustomers(cList || []);
        setEmployees(eList || []);
        setDashboardBI(biData);
        setExceptions(excList || []);
      })
      .catch((err: Error) => {
        setVisits([]);
        setError(err.message || 'Unable to load dashboard data');
      })
      .finally(() => setIsLoading(false));
  }, [
    isAdmin,
    isAuthLoading,
    user,
    selectedBrand,
    selectedZoneId,
    selectedAreaId,
    selectedEmployeeId,
    selectedAgeingBucket,
    selectedMonth,
  ]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalVisits = visits.length;
  const completedVisits = visits.filter((v) => v.status === 'COMPLETED').length;
  const inProgressVisits = visits.filter((v) => v.status === 'IN_PROGRESS').length;
  const flaggedVisits = visits.filter((v) => v.status === 'FLAGGED').length;

  const geoComplianceRate =
    totalVisits > 0 ? Math.round(((totalVisits - flaggedVisits) / totalVisits) * 100) : null;

  const formatCurrency = (val: string | number | undefined) => {
    const num = typeof val === 'string' ? parseFloat(val) : Number(val || 0);
    if (isNaN(num)) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(num);
  };

  const handleReviewException = async (exceptionId: string, status: 'APPROVED' | 'REJECTED') => {
    const notes = window.prompt(`Enter review notes for ${status.toLowerCase()}:`, '');
    if (notes === null) return;
    try {
      await apiClient.reviewFieldException(exceptionId, { status, admin_notes: notes });
      setActionSuccess(`Exception ${status.toLowerCase()} successfully.`);
      setTimeout(() => setActionSuccess(null), 3000);
      fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to review exception');
    }
  };

  const handleExportExcel = async () => {
    setIsExporting(true);
    try {
      const brandParam = selectedBrand !== 'ALL' ? selectedBrand : undefined;
      const zoneParam = selectedZoneId !== 'ALL' ? selectedZoneId : undefined;
      const areaParam = selectedAreaId !== 'ALL' ? selectedAreaId : undefined;
      const employeeParam = selectedEmployeeId !== 'ALL' ? selectedEmployeeId : undefined;
      const monthParam = selectedMonth !== 'ALL' ? selectedMonth : undefined;

      const objectUrl = await apiClient.exportOverviewExcelObjectUrl({
        brand: brandParam,
        zone_id: zoneParam,
        area_id: areaParam,
        employee_id: employeeParam,
        month: monthParam,
      });

      const dateTag = new Date().toISOString().slice(0, 10);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `executive-dashboard-summary-${dateTag}.xlsx`;
      link.click();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Excel export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportPDF = () => {
    setIsExporting(true);
    try {
      const title = 'Executive Dashboard & BI Summary';
      const headers = ['Brand', 'Dimension', 'Outlets', 'Sales', 'Collections', 'Market OS', '>90d Overdue'];
      const rows = (dashboardBI?.brand_breakdown || []).map((r) => [
        r.brand,
        r.dimension_name,
        String(r.outlets_count),
        formatCurrency(r.sales),
        formatCurrency(r.collection),
        formatCurrency(r.market_outstanding),
        formatCurrency(r.bucket_gt_90),
      ]);

      const summaryKPIs: Array<{ label: string; value: string }> = [];
      if (dashboardBI) {
        summaryKPIs.push({ label: 'Total Outlets', value: String(dashboardBI.kpis.total_outlets) });
        summaryKPIs.push({ label: 'Total Sales', value: formatCurrency(dashboardBI.kpis.total_sales) });
        summaryKPIs.push({ label: 'Market OS', value: formatCurrency(dashboardBI.kpis.total_market_outstanding) });
      }

      const pdfBytes = generatePDFContent({
        title,
        headers,
        rows,
        filters: {
          Brand: selectedBrand,
          Month: selectedMonth,
          Period: dashboardBI?.is_historical ? 'Historical Snapshot' : 'Live Data',
        },
        summaryKPIs,
      });

      const blob = new Blob([pdfBytes], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `executive-dashboard-report-${new Date().toISOString().slice(0, 10)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF export failed');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={isAdmin ? 'Executive Dashboard & BI' : 'My Day'}
        subtitle={
          isAdmin
            ? 'Unified business intelligence, real multi-brand analytics, and live field operations command center.'
            : "Today's assigned visits, collections, and check-in status."
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              onClick={fetchData}
              isLoading={isLoading}
            >
              Sync
            </Button>
            {isAdmin && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  icon={FileSpreadsheet}
                  onClick={handleExportExcel}
                  disabled={isLoading || isExporting}
                >
                  Export Excel
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  icon={Download}
                  onClick={handleExportPDF}
                  disabled={isLoading || isExporting}
                >
                  Export PDF
                </Button>
                <Button variant="secondary" size="sm" icon={Plus} onClick={() => navigate('/visits')}>
                  New Dispatch
                </Button>
              </>
            )}
          </div>
        }
      />

      {error && <ErrorBanner message={error} onRetry={fetchData} onDismiss={() => setError(null)} />}
      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          {actionSuccess}
        </div>
      )}

      {/* Global Filter Engine for Admin */}
      {isAdmin && (
        <Card variant="flat">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-primary" />
                <span className="font-label-md text-xs uppercase tracking-wider font-bold text-primary">
                  Dashboard BI Filter Engine
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-caption text-xs text-on-surface-variant">
                  Data Scope:{' '}
                  <span className="font-semibold text-primary">
                    {selectedMonth === 'ALL' ? '🟢 Current Live Data' : `🔒 Historical Snapshot (${selectedMonth})`}
                  </span>
                </span>
                <button
                  onClick={() => {
                    setSelectedMonth('ALL');
                    setSelectedBrand('ALL');
                    setSelectedZoneId('ALL');
                    setSelectedAreaId('ALL');
                    setSelectedEmployeeId('ALL');
                    setSelectedAgeingBucket('ALL');
                  }}
                  className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant hover:text-primary flex items-center gap-1 transition-colors cursor-pointer"
                >
                  <RefreshCw className="w-3 h-3" /> Reset
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* Period */}
              <div>
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Period / Month
                </label>
                <select
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                  value={selectedMonth}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                >
                  <option value="ALL">Current Live Data</option>
                  {monthlyPeriods.map((p) => {
                    const mStr = `${p.period_year}-${String(p.period_month).padStart(2, '0')}`;
                    return (
                      <option key={p.id} value={mStr}>
                        {p.period_name} {p.status === 'FINALIZED' ? '🔒 (Locked)' : '🟢 (Live)'}
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Brand */}
              <div>
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Brand
                </label>
                <select
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                  value={selectedBrand}
                  onChange={(e) => setSelectedBrand(e.target.value)}
                >
                  <option value="ALL">All Brands (Usha, VU, ZBR)</option>
                  <option value="Usha">Usha</option>
                  <option value="VU">VU</option>
                  <option value="ZBR">ZBR</option>
                </select>
              </div>

              {/* Zone */}
              <div>
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Zone (Territory)
                </label>
                <select
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                  value={selectedZoneId}
                  onChange={(e) => {
                    setSelectedZoneId(e.target.value);
                    setSelectedAreaId('ALL');
                  }}
                >
                  <option value="ALL">All Zones ({territories.length})</option>
                  {territories.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Area */}
              <div>
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Area
                </label>
                <select
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                  value={selectedAreaId}
                  onChange={(e) => setSelectedAreaId(e.target.value)}
                >
                  <option value="ALL">All Areas ({availableAreas.length})</option>
                  {availableAreas.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* FOS */}
              <div>
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  FOS / Field Officer
                </label>
                <select
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                  value={selectedEmployeeId}
                  onChange={(e) => setSelectedEmployeeId(e.target.value)}
                >
                  <option value="ALL">All Field Officers ({employeeOptions.length})</option>
                  {employeeOptions.map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name} ({emp.employee_code})
                    </option>
                  ))}
                </select>
              </div>

              {/* Ageing */}
              <div>
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Overdue Ageing
                </label>
                <select
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                  value={selectedAgeingBucket}
                  onChange={(e) => setSelectedAgeingBucket(e.target.value)}
                >
                  <option value="ALL">All Ageing Buckets</option>
                  <option value=">90">&gt;90 Days (Critical)</option>
                  <option value="75-90">75-90 Days (Severe)</option>
                  <option value="60-75">60-75 Days (High)</option>
                  <option value="45-60">45-60 Days (Medium)</option>
                  <option value="30-45">30-45 Days (Low)</option>
                  <option value="15-30">15-30 Days (Early)</option>
                  <option value="<15">&lt;15 Days (Normal)</option>
                </select>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Primary KPI Cards (Maintained exact compatibility with tests + enhanced BI) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isAdmin && (
          <MetricCard
            title="Field Representatives"
            value={employees.length}
            subtitle="Registered employee profiles"
            icon={Users}
            color="primary"
            onClick={() => navigate('/employees')}
          />
        )}
        <MetricCard
          title="Customer Accounts"
          value={customers.length}
          subtitle="Monitored geofence zones"
          icon={Building2}
          color="slate"
          onClick={isAdmin ? () => navigate('/customers') : undefined}
        />
        <MetricCard
          title={isAdmin ? 'Visits' : 'My Visits Today'}
          value={totalVisits}
          subtitle={`${completedVisits} completed, ${inProgressVisits} active`}
          icon={CalendarCheck}
          color="primary"
          onClick={() => navigate('/visits')}
        />
        <MetricCard
          title="Geo Compliance"
          value={geoComplianceRate === null ? '—' : `${geoComplianceRate}%`}
          subtitle={
            geoComplianceRate === null
              ? 'No visits recorded yet'
              : `${flaggedVisits} location anomal${flaggedVisits === 1 ? 'y' : 'ies'} flagged`
          }
          icon={ShieldCheck}
          color={geoComplianceRate !== null && geoComplianceRate < 85 ? 'amber' : 'primary'}
          onClick={isAdmin ? () => navigate('/geo-logs') : undefined}
        />
      </div>

      {/* Admin Executive BI Financial KPI Cards */}
      {isAdmin && dashboardBI && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Total Sales"
            value={formatCurrency(dashboardBI.kpis.total_sales)}
            subtitle="MIS consolidated billing"
            icon={TrendingUp}
            color="primary"
          />
          <MetricCard
            title="Total Collection"
            value={formatCurrency(dashboardBI.kpis.total_collection)}
            subtitle="Realized payments"
            icon={DollarSign}
            color="emerald"
          />
          <MetricCard
            title="Market Outstanding"
            value={formatCurrency(dashboardBI.kpis.total_market_outstanding)}
            subtitle="Total uncollected balance"
            icon={AlertTriangle}
            color="amber"
          />
          <MetricCard
            title="Critical (>90d Overdue)"
            value={formatCurrency(dashboardBI.kpis.total_overdue_gt_90)}
            subtitle="High-risk delinquent balance"
            icon={AlertOctagon}
            color="rose"
          />
        </div>
      )}

      {/* Admin Executive BI Panels */}
      {isAdmin && dashboardBI && (
        <div className="space-y-6">
          {/* Brand BI Performance */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {dashboardBI.brand_breakdown.map((brandSummary) => (
              <Card
                key={brandSummary.brand}
                variant="hover"
                className="cursor-pointer"
                onClick={() => setDrilldownRow(brandSummary)}
              >
                <div className="flex items-center justify-between mb-3">
                  <h4 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
                    {brandSummary.brand} Performance
                  </h4>
                  <span className="font-label-md text-xs text-on-surface-variant font-semibold bg-surface-container-high px-2 py-0.5 rounded">
                    {brandSummary.outlets_count} Outlets
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2.5 pt-3 border-t border-surface-container-highest">
                  <div className="p-2.5 bg-surface-container-low rounded-lg border border-surface-container-highest">
                    <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">Sales</span>
                    <span className="font-headline-sm text-sm font-bold text-primary block">
                      {formatCurrency(brandSummary.sales)}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface-container-low rounded-lg border border-surface-container-highest">
                    <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">Collections</span>
                    <span className="font-headline-sm text-sm font-bold text-primary block">
                      {formatCurrency(brandSummary.collection)}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface-container-low rounded-lg border border-surface-container-highest">
                    <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">Market OS</span>
                    <span className="font-headline-sm text-sm font-bold text-primary block">
                      {formatCurrency(brandSummary.market_outstanding)}
                    </span>
                  </div>
                  <div className="p-2.5 bg-surface-container-low rounded-lg border border-surface-container-highest">
                    <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">&gt;90d Overdue</span>
                    <span className="font-headline-sm text-sm font-bold text-error block">
                      {formatCurrency(brandSummary.bucket_gt_90)}
                    </span>
                  </div>
                </div>

                <div className="mt-3 pt-2 flex items-center justify-between text-xs text-primary font-label-md uppercase tracking-wider font-semibold border-t border-surface-container-highest">
                  <span>Drill down details</span>
                  <ChevronRight className="w-4 h-4 text-secondary-container" />
                </div>
              </Card>
            ))}
          </div>

          {/* 7-Bucket Ageing Overview & Realization Comparison */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>7-Bucket Ageing Distribution</CardTitle>
                <CardSubtitle>Market Outstanding categorized by overdue duration</CardSubtitle>
              </CardHeader>
              <div className="space-y-3">
                {Object.entries(dashboardBI.ageing_distribution).map(([bucket, amount]) => {
                  const numAmount = parseFloat(amount || '0');
                  const totalOS = parseFloat(dashboardBI.kpis.total_market_outstanding || '1');
                  const percent = totalOS > 0 ? Math.min(100, Math.round((numAmount / totalOS) * 100)) : 0;
                  const isCritical = bucket === '>90' || bucket === '75-90';

                  return (
                    <div key={bucket} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-label-md text-xs font-semibold text-on-surface">
                          {bucket.startsWith('>') ? `${bucket} Days` : `${bucket} Days`}
                        </span>
                        <span className={`font-headline-sm text-xs font-bold ${isCritical ? 'text-error' : 'text-primary'}`}>
                          {formatCurrency(amount)} ({percent}%)
                        </span>
                      </div>
                      <div className="w-full h-2 bg-surface-container-highest rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            bucket === '>90'
                              ? 'bg-error'
                              : bucket === '75-90'
                              ? 'bg-error/80'
                              : bucket === '60-75'
                              ? 'bg-secondary-container'
                              : bucket === '45-60'
                              ? 'bg-secondary-container/80'
                              : 'bg-primary-container'
                          }`}
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>

            {/* FOS Top Outlets / Field Officers */}
            <Card>
              <CardHeader>
                <CardTitle>Top Field Officers (FOS)</CardTitle>
                <CardSubtitle>Sales realization and active outlet coverage</CardSubtitle>
              </CardHeader>
              <div className="overflow-x-auto max-h-[320px]">
                <table className="w-full text-xs">
                  <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider sticky top-0 border-b border-surface-container-highest">
                    <tr>
                      <th className="px-3 py-2 text-left font-bold text-primary">FOS Name</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Brand</th>
                      <th className="px-3 py-2 text-right font-bold text-primary">Outlets</th>
                      <th className="px-3 py-2 text-right font-bold text-primary">Sales</th>
                      <th className="px-3 py-2 text-right font-bold text-primary">Market OS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest font-body-md">
                    {dashboardBI.fos_breakdown.slice(0, 8).map((fos, idx) => (
                      <tr
                        key={idx}
                        className="hover:bg-surface-container-low/70 cursor-pointer transition-colors"
                        onClick={() => setDrilldownRow(fos)}
                      >
                        <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{fos.dimension_name}</td>
                        <td className="px-3 py-2 text-on-surface-variant font-caption">{fos.brand}</td>
                        <td className="px-3 py-2 text-right text-on-surface font-semibold">{fos.outlets_count}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-primary">{formatCurrency(fos.sales)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-on-surface">{formatCurrency(fos.market_outstanding)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          {/* Operational Exceptions Review List */}
          {exceptions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="w-5 h-5 text-secondary-container" />
                  Operational Field Exceptions
                </CardTitle>
                <CardSubtitle>Review employee-filed GPS, breakdown, or closed outlet exceptions</CardSubtitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                    <tr>
                      <th className="px-3 py-2 text-left font-bold text-primary">Timestamp</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Employee</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Outlet</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Type</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Description</th>
                      <th className="px-3 py-2 text-center font-bold text-primary">Status</th>
                      <th className="px-3 py-2 text-right font-bold text-primary">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest font-body-md">
                    {exceptions.map((exc) => (
                      <tr key={exc.id} className="hover:bg-surface-container-low/70 transition-colors">
                        <td className="px-3 py-2 text-on-surface-variant font-caption">{new Date(exc.created_at).toLocaleString()}</td>
                        <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{exc.employee_name || '-'}</td>
                        <td className="px-3 py-2 text-on-surface">{exc.customer_name || '-'}</td>
                        <td className="px-3 py-2">
                          <span className="font-label-md text-[10px] bg-surface-container-high px-2 py-0.5 rounded text-on-surface font-semibold">
                            {exc.exception_type}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-on-surface-variant max-w-xs truncate font-caption">{exc.description}</td>
                        <td className="px-3 py-2 text-center">
                          <StatusBadge status={exc.status} size="sm" />
                        </td>
                        <td className="px-3 py-2 text-right">
                          {exc.status === 'PENDING_REVIEW' && (
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleReviewException(exc.id, 'APPROVED')}
                                className="p-1 rounded bg-primary-container text-on-primary-container hover:opacity-90 cursor-pointer"
                                title="Approve Exception"
                              >
                                <Check className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleReviewException(exc.id, 'REJECTED')}
                                className="p-1 rounded bg-error-container text-on-error-container hover:opacity-90 cursor-pointer"
                                title="Reject Exception"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Main Operational Visits Table (Preserved for compatibility and operations) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card variant="default" className="lg:col-span-2 flex flex-col justify-between">
          <div>
            <CardHeader>
              <div>
                <CardTitle>{isAdmin ? 'Recent Field Operations' : "Today's Visits"}</CardTitle>
                <CardSubtitle>Live visit status feed and check-in times</CardSubtitle>
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon={ArrowUpRight}
                onClick={() => navigate('/visits')}
              >
                View All
              </Button>
            </CardHeader>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-body-md text-on-surface">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md text-xs uppercase tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Customer</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Scheduled</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Check-In</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest">
                  {isLoading ? (
                    Array.from({ length: 4 }).map((_, idx) => (
                      <tr key={idx} className="animate-pulse">
                        <td colSpan={4} className="px-space-4 py-space-3.5">
                          <div className="h-4 bg-surface-container-high rounded w-3/4"></div>
                        </td>
                      </tr>
                    ))
                  ) : visits.length === 0 ? (
                    <tr>
                      <td
                        colSpan={4}
                        className="px-space-4 py-space-8 text-center text-on-surface-variant font-caption"
                      >
                        {isAdmin
                          ? 'No visit activity recorded.'
                          : 'Nothing scheduled for today. Enjoy the breather.'}
                      </td>
                    </tr>
                  ) : (
                    visits.slice(0, 6).map((visit) => (
                      <tr
                        key={visit.id}
                        onClick={() => navigate(`/visits/${visit.id}`)}
                        className="hover:bg-surface-container-low/80 cursor-pointer transition-colors duration-150"
                      >
                        <td className="px-space-4 py-space-3.5 font-headline-sm text-sm text-primary font-semibold">
                          {visit.customer_name ||
                            customers.find((c) => c.id === visit.customer_id)?.name ||
                            `Customer #${visit.customer_id.substring(0, 8)}`}
                        </td>
                        <td className="px-space-4 py-space-3.5 font-caption text-xs text-on-surface-variant">
                          {new Date(visit.scheduled_at).toLocaleString()}
                        </td>
                        <td className="px-space-4 py-space-3.5">
                          <StatusBadge status={visit.status} size="sm" />
                        </td>
                        <td className="px-space-4 py-space-3.5 font-label-md text-xs text-on-surface-variant">
                          {visit.check_in_at ? (
                            new Date(visit.check_in_at).toLocaleTimeString()
                          ) : (
                            <span className="text-outline">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Card>

        {/* Quick Actions & System Telemetry Guard */}
        <div className="space-y-6 flex flex-col justify-between">
          <Card variant="default">
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <div className="space-y-3">
              <button
                onClick={() => navigate('/visits')}
                className="w-full text-left p-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary transition-colors">
                    {isAdmin ? 'Visit Dispatch' : 'My Visits'}
                  </p>
                  <p className="font-caption text-xs text-on-surface-variant">
                    {isAdmin ? "View and assign today's schedule" : 'Open your assigned visits'}
                  </p>
                </div>
                <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </button>

              {isAdmin && (
                <>
                  <button
                    onClick={() => navigate('/reports')}
                    className="w-full text-left p-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <div>
                      <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary transition-colors">
                        Business Reports &amp; Exports
                      </p>
                      <p className="font-caption text-xs text-on-surface-variant">
                        Access detailed BI and monthly reports
                      </p>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                  </button>

                  <button
                    onClick={() => navigate('/geo-logs')}
                    className="w-full text-left p-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <div>
                      <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary transition-colors">
                        Geo Audit Trail
                      </p>
                      <p className="font-caption text-xs text-on-surface-variant">
                        Inspect GPS coordinate logs
                      </p>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                  </button>
                </>
              )}
            </div>
          </Card>

          <Card variant="flat" className="bg-primary-tint/20 border-primary-fixed-dim">
            <div className="flex items-center gap-2.5 text-primary mb-2">
              <AlertOctagon className="w-5 h-5 shrink-0 text-secondary-container" />
              <h4 className="font-headline-sm text-sm font-bold text-primary">
                System Telemetry Guard
              </h4>
            </div>
            <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
              Check-in location is verified against each customer&apos;s own geofence radius. Mock
              location signals are flagged automatically for review.
            </p>
          </Card>
        </div>
      </div>

      {/* Drilldown Modal */}
      {drilldownRow && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-on-surface/50 backdrop-blur-xs">
          <div className="bg-surface border border-surface-container-highest rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl text-on-surface">
            <div className="flex items-center justify-between border-b border-surface-container-highest pb-3">
              <h3 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                <Eye className="w-5 h-5 text-secondary-container" />
                {drilldownRow.brand} - {drilldownRow.dimension_name}
              </h3>
              <button
                onClick={() => setDrilldownRow(null)}
                className="p-1 text-on-surface-variant hover:text-on-surface rounded-lg cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block">Outlets Count</span>
                <span className="font-headline-sm text-base font-bold text-primary">{drilldownRow.outlets_count}</span>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block">Sales Amount</span>
                <span className="font-headline-sm text-base font-bold text-primary">{formatCurrency(drilldownRow.sales)}</span>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block">Collections Realized</span>
                <span className="font-headline-sm text-base font-bold text-primary">{formatCurrency(drilldownRow.collection)}</span>
              </div>
              <div className="p-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block">Market Outstanding</span>
                <span className="font-headline-sm text-base font-bold text-primary">{formatCurrency(drilldownRow.market_outstanding)}</span>
              </div>
            </div>

            <div className="pt-2 border-t border-surface-container-highest">
              <span className="font-label-md text-xs uppercase tracking-wider font-semibold text-on-surface-variant block mb-2">Ageing Buckets:</span>
              <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                <div className="p-2 rounded bg-surface-container-low border border-surface-container-highest">&lt;15d: {formatCurrency(drilldownRow.bucket_lt_15)}</div>
                <div className="p-2 rounded bg-surface-container-low border border-surface-container-highest">15-30d: {formatCurrency(drilldownRow.bucket_15_30)}</div>
                <div className="p-2 rounded bg-surface-container-low border border-surface-container-highest">30-45d: {formatCurrency(drilldownRow.bucket_30_45)}</div>
                <div className="p-2 rounded bg-surface-container-low border border-surface-container-highest">45-60d: {formatCurrency(drilldownRow.bucket_45_60)}</div>
                <div className="p-2 rounded bg-surface-container-low border border-surface-container-highest">60-75d: {formatCurrency(drilldownRow.bucket_60_75)}</div>
                <div className="p-2 rounded bg-surface-container-low border border-surface-container-highest">&gt;90d: <span className="text-error font-bold">{formatCurrency(drilldownRow.bucket_gt_90)}</span></div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => setDrilldownRow(null)}>
                Close
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setDrilldownRow(null);
                  navigate('/reports');
                }}
              >
                Open Full Report
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  CheckCircle2,
  TrendingUp,
  Users,
  Download,
  Calendar,
  Building2,
  Search,
  FileSpreadsheet,
  Lock,
  Unlock,
  Filter,
  RefreshCw,
  Clock,
  DollarSign,
  AlertTriangle,
  ArrowRight,
  Sparkles,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';
import { CollectionsOverviewPage } from './CollectionsOverviewPage';
import { apiClient } from '../api/client';
import { generatePDFContent } from '../utils/pdf-report';
import {
  BusinessBIDashboard,
  EmployeeReportRow,
  EmployeeMasterReportRow,
  GeoReportRow,
  OutletReportRow,
  OutstandingAgeingReportRow,
  VisitDetailedReportRow,
  MonthlyReportingPeriod,
  Territory,
  Area,
  Employee,
} from '../types';

interface DateRange {
  startDate: string;
  endDate: string;
}

export type TabType =
  | 'financial_bi'
  | 'business_bi'
  | 'collections_workbench'
  | 'outstanding'
  | 'outlets'
  | 'employees'
  | 'visits'
  | 'monthly';

export const ReportsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get('tab') as TabType | null;
  const initialTab: TabType = rawTab && ['financial_bi', 'business_bi', 'collections_workbench', 'outstanding', 'outlets', 'employees', 'visits', 'monthly'].includes(rawTab)
    ? (rawTab === 'business_bi' ? 'financial_bi' : rawTab)
    : 'financial_bi';

  // Navigation State
  const [activeTab, setActiveTab] = useState<TabType>(initialTab);
  const [biSubTab, setBiSubTab] = useState<'brand' | 'zone' | 'area' | 'fos' | 'raw'>('brand');
  const [visitSubView, setVisitSubView] = useState<'register' | 'geo'>('register');

  useEffect(() => {
    const tabParam = searchParams.get('tab') as TabType;
    if (tabParam && ['financial_bi', 'business_bi', 'collections_workbench', 'outstanding', 'outlets', 'employees', 'visits', 'monthly'].includes(tabParam)) {
      setActiveTab(tabParam === 'business_bi' ? 'financial_bi' : tabParam);
    }
  }, [searchParams]);

  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', tab);
      return next;
    });
  };

  // Filter State
  const [selectedMonth, setSelectedMonth] = useState<string>('ALL');
  const [selectedBrand, setSelectedBrand] = useState<string>('ALL');
  const [selectedZoneId, setSelectedZoneId] = useState<string>('ALL');
  const [selectedAreaId, setSelectedAreaId] = useState<string>('ALL');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('ALL');
  const [selectedAgeingBucket, setSelectedAgeingBucket] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [dateRange, setDateRange] = useState<DateRange>({ startDate: '', endDate: '' });
  const [appliedDateRange, setAppliedDateRange] = useState<DateRange>({ startDate: '', endDate: '' });
  const [dateError, setDateError] = useState<string | null>(null);

  // Master Data Options for Filters
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [employeeOptions, setEmployeeOptions] = useState<Employee[]>([]);
  const [monthlyPeriods, setMonthlyPeriods] = useState<MonthlyReportingPeriod[]>([]);

  // Report Datasets
  const [businessBI, setBusinessBI] = useState<BusinessBIDashboard | null>(null);
  const [employeeReport, setEmployeeReport] = useState<EmployeeReportRow[]>([]);
  const [employeeMasterList, setEmployeeMasterList] = useState<EmployeeMasterReportRow[]>([]);
  const [outletsList, setOutletsList] = useState<OutletReportRow[]>([]);
  const [outstandingList, setOutstandingList] = useState<OutstandingAgeingReportRow[]>([]);
  const [visitsList, setVisitsList] = useState<VisitDetailedReportRow[]>([]);
  const [geoReport, setGeoReport] = useState<GeoReportRow[]>([]);

  // Status & Async State
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Load Reference Data (Territories, Areas, Employees, Monthly Periods)
  useEffect(() => {
    const loadMasters = async () => {
      try {
        const [tList, aList, eList, pList] = await Promise.all([
          apiClient.getTerritories().catch(() => [] as Territory[]),
          apiClient.getAreas().catch(() => [] as Area[]),
          apiClient.getEmployees().catch(() => [] as Employee[]),
          apiClient.getMonthlyPeriods().catch(() => [] as MonthlyReportingPeriod[]),
        ]);
        setTerritories(tList || []);
        setAreas(aList || []);
        setEmployeeOptions(eList || []);
        setMonthlyPeriods(pList || []);
      } catch (err) {
        console.error('Failed to load master filters', err);
      }
    };
    loadMasters();
  }, []);

  // Filtered areas cascading with selected Zone
  const availableAreas = useMemo(() => {
    if (selectedZoneId === 'ALL') return areas;
    return areas.filter((a) => a.territory_id === selectedZoneId);
  }, [areas, selectedZoneId]);

  // Main Data Loader based on Active Tab and Applied Filters
  const loadActiveReport = useCallback(async () => {
    setIsLoading(true);
    try {
      const brandParam = selectedBrand !== 'ALL' ? selectedBrand : undefined;
      const zoneParam = selectedZoneId !== 'ALL' ? selectedZoneId : undefined;
      const areaParam = selectedAreaId !== 'ALL' ? selectedAreaId : undefined;
      const employeeParam = selectedEmployeeId !== 'ALL' ? selectedEmployeeId : undefined;
      const ageingParam = selectedAgeingBucket !== 'ALL' ? selectedAgeingBucket : undefined;
      const monthParam = selectedMonth !== 'ALL' ? selectedMonth : undefined;

      const [empRes, geoRes] = await Promise.all([
        apiClient.getEmployeeReport(appliedDateRange.startDate || undefined, appliedDateRange.endDate || undefined).catch(() => [] as EmployeeReportRow[]),
        apiClient.getGeoVerificationReport(appliedDateRange.startDate || undefined, appliedDateRange.endDate || undefined).catch(() => [] as GeoReportRow[]),
      ]);

      setEmployeeReport(empRes || []);
      setGeoReport(geoRes || []);

      // Load additional endpoints based on active tab
      if (activeTab === 'financial_bi' || activeTab === 'business_bi' || activeTab === 'monthly') {
        const biRes = await apiClient.getBusinessSummary(brandParam, zoneParam, areaParam, employeeParam, monthParam).catch(() => null);
        setBusinessBI(biRes);
      } else if (activeTab === 'employees') {
        const masterRes = await apiClient.getEmployeesMasterReport({ query: searchQuery || undefined }).catch(() => [] as EmployeeMasterReportRow[]);
        setEmployeeMasterList(masterRes || []);
      } else if (activeTab === 'outlets') {
        const outRes = await apiClient.getOutletsReport({
          brand: brandParam,
          zone_id: zoneParam,
          area_id: areaParam,
          employee_id: employeeParam,
          query: searchQuery || undefined,
        }).catch(() => [] as OutletReportRow[]);
        setOutletsList(outRes || []);
      } else if (activeTab === 'outstanding') {
        const osRes = await apiClient.getOutstandingReport({
          brand: brandParam,
          zone_id: zoneParam,
          area_id: areaParam,
          employee_id: employeeParam,
          ageing_bucket: ageingParam,
          month: monthParam,
          query: searchQuery || undefined,
        }).catch(() => [] as OutstandingAgeingReportRow[]);
        setOutstandingList(osRes || []);
      } else if (activeTab === 'visits') {
        const visRes = await apiClient.getVisitsDetailedReport({
          start_date: appliedDateRange.startDate || undefined,
          end_date: appliedDateRange.endDate || undefined,
          employee_id: employeeParam,
          zone_id: zoneParam,
          area_id: areaParam,
        }).catch(() => [] as VisitDetailedReportRow[]);
        setVisitsList(visRes || []);
      }
    } catch (err) {
      console.error('Report loader error', err);
    } finally {
      setIsLoading(false);
    }
  }, [
    activeTab,
    selectedBrand,
    selectedZoneId,
    selectedAreaId,
    selectedEmployeeId,
    selectedAgeingBucket,
    selectedMonth,
    searchQuery,
    appliedDateRange,
  ]);

  useEffect(() => {
    loadActiveReport();
  }, [loadActiveReport]);

  const handleDateChange = (field: keyof DateRange, value: string) => {
    setDateRange((prev) => ({ ...prev, [field]: value }));
  };

  const applyDateFilter = () => {
    if (dateRange.startDate && dateRange.endDate) {
      const start = new Date(dateRange.startDate);
      const end = new Date(dateRange.endDate);
      if (end < start) {
        setDateError('End date must be after start date');
        return;
      }
    }
    setDateError(null);
    setAppliedDateRange({ ...dateRange });
  };

  const clearDateFilter = () => {
    setDateRange({ startDate: '', endDate: '' });
    setAppliedDateRange({ startDate: '', endDate: '' });
    setDateError(null);
  };

  const resetAllFilters = () => {
    setSelectedMonth('ALL');
    setSelectedBrand('ALL');
    setSelectedZoneId('ALL');
    setSelectedAreaId('ALL');
    setSelectedEmployeeId('ALL');
    setSelectedAgeingBucket('ALL');
    setSearchQuery('');
    clearDateFilter();
  };

  const formatCurrency = (val: string | number | undefined) => {
    const num = typeof val === 'string' ? parseFloat(val) : Number(val || 0);
    if (isNaN(num)) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(num);
  };

  // ---------------------------------------------------------------------------
  // Export Handlers
  // ---------------------------------------------------------------------------
  const exportCSV = (data: Record<string, unknown>[], filenamePrefix: string) => {
    if (!data.length) return;
    const headers = Object.keys(data[0]);
    const csvContent = [
      headers.join(','),
      ...data.map((row) =>
        headers
          .map((h) => {
            const val = row[h];
            if (val === null || val === undefined) return '""';
            return `"${String(val).replace(/"/g, '""')}"`;
          })
          .join(',')
      ),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filenamePrefix}-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleExportExcel = async () => {
    setIsExporting(true);
    try {
      let objectUrl = '';
      const dateTag = new Date().toISOString().slice(0, 10);
      let filename = `FieldTrack_${activeTab}_${dateTag}.xlsx`;

      const brandParam = selectedBrand !== 'ALL' ? selectedBrand : undefined;
      const zoneParam = selectedZoneId !== 'ALL' ? selectedZoneId : undefined;
      const areaParam = selectedAreaId !== 'ALL' ? selectedAreaId : undefined;
      const employeeParam = selectedEmployeeId !== 'ALL' ? selectedEmployeeId : undefined;
      const ageingParam = selectedAgeingBucket !== 'ALL' ? selectedAgeingBucket : undefined;
      const monthParam = selectedMonth !== 'ALL' ? selectedMonth : undefined;

      switch (activeTab) {
        case 'financial_bi':
        case 'business_bi':
          objectUrl = await apiClient.exportBusinessSummaryExcelObjectUrl(
            brandParam,
            zoneParam,
            areaParam,
            employeeParam,
            monthParam
          );
          filename = `financial-bi-report-${dateTag}.xlsx`;
          break;
        case 'employees':
          objectUrl = await apiClient.exportEmployeesMasterExcelObjectUrl({
            query: searchQuery || undefined,
          });
          filename = `employee-report-${dateTag}.xlsx`;
          break;
        case 'outlets':
          objectUrl = await apiClient.exportOutletsExcelObjectUrl({
            brand: brandParam,
            zone_id: zoneParam,
            area_id: areaParam,
            employee_id: employeeParam,
            query: searchQuery || undefined,
          });
          filename = `outlet-report-${dateTag}.xlsx`;
          break;
        case 'outstanding':
          objectUrl = await apiClient.exportOutstandingExcelObjectUrl({
            brand: brandParam,
            zone_id: zoneParam,
            area_id: areaParam,
            employee_id: employeeParam,
            ageing_bucket: ageingParam,
            month: monthParam,
            query: searchQuery || undefined,
          });
          filename = `outstanding-ageing-report-${dateTag}.xlsx`;
          break;
        case 'collections_workbench':
          objectUrl = await apiClient.exportCollectionsExcelObjectUrl({
            brand: brandParam,
            zone_id: zoneParam,
            area_id: areaParam,
            employee_id: employeeParam,
            month: monthParam,
            query: searchQuery || undefined,
          });
          filename = `collections-report-${dateTag}.xlsx`;
          break;
        case 'visits':
          objectUrl = await apiClient.exportVisitsDetailedExcelObjectUrl({
            start_date: appliedDateRange.startDate || undefined,
            end_date: appliedDateRange.endDate || undefined,
            employee_id: employeeParam,
            zone_id: zoneParam,
            area_id: areaParam,
          });
          filename = `visits-report-${dateTag}.xlsx`;
          break;
        case 'monthly':
          objectUrl = await apiClient.exportBusinessSummaryExcelObjectUrl(
            brandParam,
            zoneParam,
            areaParam,
            employeeParam,
            selectedMonth !== 'ALL' ? selectedMonth : undefined
          );
          filename = `monthly-snapshot-${selectedMonth}-${dateTag}.xlsx`;
          break;
        default:
          objectUrl = await apiClient.exportBusinessSummaryExcelObjectUrl();
          break;
      }

      if (objectUrl) {
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(objectUrl);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Excel export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportPDF = () => {
    setIsExporting(true);
    try {
      let title = 'Report';
      let filenamePrefix = 'report';
      let headers: string[] = [];
      let rows: string[][] = [];
      const filterSummary: Record<string, string> = {
        Brand: selectedBrand,
        Month: selectedMonth,
        Bucket: selectedAgeingBucket,
      };

      const summaryKPIs: Array<{ label: string; value: string }> = [];

      if (businessBI) {
        summaryKPIs.push({ label: 'Outlets', value: String(businessBI.total_outlets) });
        summaryKPIs.push({ label: 'Sales', value: formatCurrency(businessBI.total_sales) });
        summaryKPIs.push({ label: 'OS', value: formatCurrency(businessBI.total_market_outstanding) });
      }

      if ((activeTab === 'financial_bi' || activeTab === 'business_bi') && businessBI) {
        title = 'Financial & Business Intelligence Report';
        filenamePrefix = 'financial-bi-report';
        headers = ['Brand', 'Dimension', 'Outlets', 'Sales', 'Collection', 'Market OS', '>90d'];
        const activeRows =
          biSubTab === 'brand'
            ? businessBI.brand_summaries
            : biSubTab === 'zone'
            ? businessBI.zone_summaries
            : biSubTab === 'area'
            ? businessBI.area_summaries
            : biSubTab === 'fos'
            ? businessBI.fos_summaries
            : businessBI.raw_outlet_rows;

        rows = activeRows.map((r) => [
          r.brand,
          r.dimension_name,
          String(r.outlets_count),
          formatCurrency(r.sales),
          formatCurrency(r.collection),
          formatCurrency(r.market_outstanding),
          formatCurrency(r.bucket_gt_90),
        ]);
      } else if (activeTab === 'outlets') {
        title = 'Outlets Directory Report';
        filenamePrefix = 'outlet-report';
        headers = ['DMS Code', 'Outlet Name', 'Zone', 'Area', 'FOS', 'Location Status', 'Market OS'];
        rows = outletsList.map((o) => [
          o.dms_code || '',
          o.outlet_name,
          o.zone_name || '',
          o.area_name || '',
          o.fos_name || '',
          o.location_status,
          formatCurrency(o.market_outstanding),
        ]);
      } else if (activeTab === 'outstanding') {
        title = 'Market Outstanding & Ageing Report';
        filenamePrefix = 'outstanding-ageing-report';
        headers = ['Brand', 'DMS Code', 'Outlet Name', 'Zone', 'FOS', 'Total OS', '>90d Overdue', 'Severity'];
        rows = outstandingList.map((o) => [
          o.brand,
          o.dms_code || '',
          o.outlet_name,
          o.zone_name || '',
          o.fos_name || '',
          formatCurrency(o.market_outstanding),
          formatCurrency(o.bucket_gt_90),
          o.highest_overdue_bucket,
        ]);
      } else if (activeTab === 'employees') {
        title = 'Employee Report';
        filenamePrefix = 'employee-report';
        headers = ['Employee ID', 'Employee Name', 'Total Visits', 'Completed Visits', 'Pending Visits', 'Missed Visits', 'Flagged Visits', 'Completion Rate'];
        rows = employeeReport.map((e) => [
          e.employee_id,
          e.employee_name,
          String(e.total_visits),
          String(e.completed_visits),
          String(e.pending_visits),
          String(e.missed_visits),
          String(e.flagged_visits),
          `${e.completion_rate}%`,
        ]);
      } else if (activeTab === 'visits') {
        if (visitSubView === 'geo') {
          title = 'Geo Verification Report';
          filenamePrefix = 'geo-verification-report';
          headers = ['Visit ID', 'Employee Name', 'Customer Name', 'Attempted At', 'Verification Type', 'Valid', 'Distance (m)', 'Failure Reason'];
          rows = geoReport.map((g) => [
            g.visit_id,
            g.employee_name,
            g.customer_name,
            g.attempted_at,
            g.verification_type,
            g.is_valid ? 'Yes' : 'No',
            String(g.distance_m),
            g.failure_reason || '',
          ]);
        } else {
          title = 'Operational Visits Report';
          filenamePrefix = 'visits-report';
          headers = ['Scheduled Date', 'Employee', 'Outlet', 'DMS Code', 'Zone', 'Status', 'Check-In', 'Check-Out', 'Duration', 'GPS'];
          rows = visitsList.map((v) => [
            new Date(v.scheduled_at).toLocaleDateString(),
            v.employee_name,
            v.customer_name,
            v.dms_code || '',
            v.zone_name || '',
            v.status,
            v.check_in_at ? new Date(v.check_in_at).toLocaleTimeString() : '',
            v.check_out_at ? new Date(v.check_out_at).toLocaleTimeString() : '',
            v.duration_minutes ? `${v.duration_minutes}m` : '',
            v.is_gps_verified ? 'Yes' : 'No',
          ]);
        }
      } else {
        title = `${activeTab.toUpperCase()} Report`;
        filenamePrefix = `${activeTab}-report`;
        headers = ['Metric', 'Value'];
        rows = [['Status', 'Active'], ['Generated', new Date().toLocaleString()]];
      }

      const pdfBytes = generatePDFContent({
        title,
        headers,
        rows,
        dateRange: appliedDateRange,
        filters: filterSummary,
        summaryKPIs,
      });

      const blob = new Blob([pdfBytes], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${filenamePrefix}-${new Date().toISOString().slice(0, 10)}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'PDF export failed');
    } finally {
      setIsExporting(false);
    }
  };

  // Month Finalization / Reopen
  const handleFinalizeMonth = async (period: MonthlyReportingPeriod) => {
    if (!window.confirm(`Are you sure you want to finalize and lock the monthly snapshot for ${period.period_name}? Once finalized, historical figures cannot be modified.`)) {
      return;
    }
    try {
      const updated = await apiClient.finalizeMonthlyPeriod(period.id);
      setMonthlyPeriods((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionSuccess(`Monthly period ${period.period_name} finalized and locked successfully.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to finalize month');
    }
  };

  const handleReopenMonth = async (period: MonthlyReportingPeriod) => {
    if (!window.confirm(`Reopen ${period.period_name}? This will remove the finalized lock.`)) return;
    try {
      const updated = await apiClient.reopenMonthlyPeriod(period.id);
      setMonthlyPeriods((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionSuccess(`Monthly period ${period.period_name} reopened.`);
      setTimeout(() => setActionSuccess(null), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reopen month');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title="Reports & Collections"
        subtitle="Live business intelligence, credit recovery workbench, operational audits, and monthly snapshots"
      />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          {actionSuccess}
        </div>
      )}

      {/* Global Filter Engine */}
      <Card variant="flat">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-primary" />
              <span className="font-label-md text-xs uppercase tracking-wider font-bold text-primary">
                Global Filter Engine
              </span>
            </div>
            <button
              onClick={resetAllFilters}
              className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant hover:text-primary flex items-center gap-1 transition-colors cursor-pointer"
            >
              <RefreshCw className="w-3 h-3" /> Reset Filters
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {/* Month Filter */}
            <div>
              <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                Month Period
              </label>
              <select
                className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
              >
                <option value="ALL">All Available Months</option>
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

            {/* Brand Filter */}
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

            {/* Zone Filter */}
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

            {/* Area Filter */}
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

            {/* FOS / Employee Filter */}
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

            {/* Ageing Bucket Filter */}
            <div>
              <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                Ageing Bucket
              </label>
              <select
                className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
                value={selectedAgeingBucket}
                onChange={(e) => setSelectedAgeingBucket(e.target.value)}
              >
                <option value="ALL">All Overdue Buckets</option>
                <option value=">90">Critical (&gt;90 Days)</option>
                <option value="75-90">Severe (75-90 Days)</option>
                <option value="60-75">High (60-75 Days)</option>
                <option value="45-60">Medium (45-60 Days)</option>
                <option value="30-45">Low (30-45 Days)</option>
                <option value="15-30">Early (15-30 Days)</option>
                <option value="<15">Normal (&lt;15 Days)</option>
              </select>
            </div>
          </div>

          {/* Search bar & Operational Date Filter */}
          <div className="pt-2 border-t border-surface-container-highest flex flex-wrap items-center justify-between gap-3">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-on-surface-variant" />
              <input
                type="text"
                placeholder="Search DMS code, outlet, or officer..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-9 bg-surface border border-outline-variant rounded-lg pl-8 pr-3 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold">Date Range:</span>
              <input
                type="date"
                aria-label="Start date"
                value={dateRange.startDate}
                onChange={(e) => handleDateChange('startDate', e.target.value)}
                className="h-8 bg-surface border border-outline-variant rounded-md px-2 py-1 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container"
              />
              <span className="text-on-surface-variant text-xs font-caption">to</span>
              <input
                type="date"
                aria-label="End date"
                value={dateRange.endDate}
                onChange={(e) => handleDateChange('endDate', e.target.value)}
                className="h-8 bg-surface border border-outline-variant rounded-md px-2 py-1 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container"
              />
              <Button size="sm" variant="secondary" onClick={applyDateFilter} className="h-8 text-xs py-1">
                Apply Filter
              </Button>
              <Button size="sm" variant="outline" onClick={clearDateFilter} className="h-8 text-xs py-1">
                Clear
              </Button>
            </div>
          </div>

          {/* Date Error */}
          {dateError && (
            <p className="text-xs text-error font-medium pt-1">{dateError}</p>
          )}

          {/* Active Filter Indicator */}
          {(appliedDateRange.startDate || appliedDateRange.endDate || selectedBrand !== 'ALL' || selectedMonth !== 'ALL') && (
            <div className="font-caption text-xs text-primary font-medium pt-1">
              Active filter: {appliedDateRange.startDate || 'Start'} to {appliedDateRange.endDate || 'End'}{' '}
              {selectedBrand !== 'ALL' ? `| Brand: ${selectedBrand}` : ''}{' '}
              {selectedMonth !== 'ALL' ? `| Month: ${selectedMonth}` : ''}
            </div>
          )}
        </div>
      </Card>

      {/* Navigation Tabs */}
      <div className="flex flex-wrap gap-1.5 border-b border-surface-container-highest pb-2">
        {[
          { id: 'financial_bi', label: 'business_bi', display: 'Financial & BI', icon: TrendingUp },
          { id: 'collections_workbench', label: 'collections', display: 'Collections Workbench', icon: DollarSign },
          { id: 'outstanding', label: 'outstanding', display: 'Outstanding & Ageing', icon: AlertTriangle },
          { id: 'outlets', label: 'outlets', display: 'Outlets', icon: Building2 },
          { id: 'employees', label: 'employees', display: 'Field Staff', icon: Users },
          { id: 'visits', label: 'visits', display: 'Visits & GPS', icon: Clock },
          { id: 'monthly', label: 'monthly', display: 'Monthly Snapshots', icon: Calendar },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id || (tab.id === 'financial_bi' && activeTab === 'business_bi');
          return (
            <button
              key={tab.id}
              role="button"
              name={tab.label}
              aria-label={tab.label}
              onClick={() => handleTabChange(tab.id as TabType)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-label-md uppercase tracking-wider font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-primary-container text-on-primary-container shadow-xs border border-primary-container'
                  : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container border border-transparent'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-secondary-container' : 'text-on-surface-variant'}`} />
              {tab.display}
            </button>
          );
        })}
      </div>

      {/* TAB 1: FINANCIAL BI */}
      {(activeTab === 'financial_bi' || activeTab === 'business_bi') && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-container-highest pb-2">
            <div className="flex flex-wrap items-center gap-2">
              {(['brand', 'zone', 'area', 'fos', 'raw'] as const).map((sub) => (
                <button
                  key={sub}
                  onClick={() => setBiSubTab(sub)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-label-md uppercase tracking-wider font-semibold transition-all cursor-pointer ${
                    biSubTab === sub
                      ? 'bg-primary-container text-on-primary-container shadow-xs border border-primary-container'
                      : 'bg-surface border border-outline-variant text-on-surface-variant hover:text-on-surface hover:bg-surface-container'
                  }`}
                >
                  {sub === 'brand' && 'Brand Summary'}
                  {sub === 'zone' && 'Zone Summary'}
                  {sub === 'area' && 'Area Summary'}
                  {sub === 'fos' && 'FOS Summary'}
                  {sub === 'raw' && 'Raw Outlets Data'}
                </button>
              ))}
            </div>
            {businessBI && (
              <div className="font-caption text-xs text-on-surface-variant">
                Total Outlets: <span className="font-semibold text-primary">{businessBI.total_outlets}</span> | Total OS: <span className="font-semibold text-primary font-headline-sm">{formatCurrency(businessBI.total_market_outstanding)}</span>
              </div>
            )}
          </div>

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-3 py-2.5 text-left font-bold text-primary">Brand</th>
                    {biSubTab === 'raw' ? (
                      <>
                        <th className="px-3 py-2.5 text-left font-bold text-primary">DMS Code</th>
                        <th className="px-3 py-2.5 text-left font-bold text-primary">Outlet Name</th>
                        <th className="px-3 py-2.5 text-left font-bold text-primary">Zone</th>
                        <th className="px-3 py-2.5 text-left font-bold text-primary">FOS</th>
                      </>
                    ) : (
                      <>
                        <th className="px-3 py-2.5 text-left font-bold text-primary">Dimension Name</th>
                        <th className="px-3 py-2.5 text-right font-bold text-primary">Outlets</th>
                      </>
                    )}
                    <th className="px-3 py-2.5 text-right font-bold text-primary">Sales</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">Collection</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">Market OS</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">&lt;15d</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">15-30d</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">30-45d</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">45-60d</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">60-75d</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">75-90d</th>
                    <th className="px-3 py-2.5 text-right font-bold text-primary">&gt;90d</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest font-body-md">
                  {businessBI ? (
                    (biSubTab === 'brand'
                      ? businessBI.brand_summaries
                      : biSubTab === 'zone'
                      ? businessBI.zone_summaries
                      : biSubTab === 'area'
                      ? businessBI.area_summaries
                      : biSubTab === 'fos'
                      ? businessBI.fos_summaries
                      : businessBI.raw_outlet_rows
                    ).map((r, idx) => (
                      <tr key={idx} className="hover:bg-surface-container-low/70 transition-colors">
                        <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{r.brand}</td>
                        {biSubTab === 'raw' ? (
                          <>
                            <td className="px-3 py-2 font-mono text-xs text-primary font-semibold">{r.dms_code || '-'}</td>
                            <td className="px-3 py-2 font-semibold text-on-surface">{r.outlet_name}</td>
                            <td className="px-3 py-2 text-on-surface-variant font-caption">{r.zone_name}</td>
                            <td className="px-3 py-2 text-on-surface-variant font-caption">{r.fos_name}</td>
                          </>
                        ) : (
                          <>
                            <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{r.dimension_name}</td>
                            <td className="px-3 py-2 text-right text-on-surface font-semibold">{r.outlets_count}</td>
                          </>
                        )}
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-primary">{formatCurrency(r.sales)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-primary">{formatCurrency(r.collection)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-on-surface">{formatCurrency(r.market_outstanding)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_lt_15)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_15_30)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_30_45)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_45_60)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface">{formatCurrency(r.bucket_60_75)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface">{formatCurrency(r.bucket_75_90)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-error">{formatCurrency(r.bucket_gt_90)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={13} className="text-center py-6 text-on-surface-variant font-caption">
                        Loading financial dataset...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 3: OUTSTANDING & AGEING */}
      {activeTab === 'outstanding' && (
        <Card>
          <CardHeader>
            <CardTitle>Market Outstanding &amp; Ageing Buckets</CardTitle>
            <CardSubtitle>Accounts with open balances grouped across 7 overdue intervals</CardSubtitle>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-3 py-2 text-left font-bold text-primary">Brand</th>
                  <th className="px-3 py-2 text-left font-bold text-primary">DMS Code</th>
                  <th className="px-3 py-2 text-left font-bold text-primary">Outlet Name</th>
                  <th className="px-3 py-2 text-left font-bold text-primary">Zone</th>
                  <th className="px-3 py-2 text-left font-bold text-primary">FOS</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">Market OS</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">&lt;15d</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">15-30d</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">30-45d</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">45-60d</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">60-75d</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">75-90d</th>
                  <th className="px-3 py-2 text-right font-bold text-primary">&gt;90d</th>
                  <th className="px-3 py-2 text-center font-bold text-primary">Severity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest font-body-md">
                {outstandingList.length === 0 ? (
                  <tr>
                    <td colSpan={14} className="text-center py-8 text-on-surface-variant font-caption">
                      No outstanding accounts found matching the current filters.
                    </td>
                  </tr>
                ) : (
                  outstandingList.map((r, i) => (
                    <tr key={i} className="hover:bg-surface-container-low/70 transition-colors">
                      <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{r.brand}</td>
                      <td className="px-3 py-2 font-mono text-xs text-primary font-semibold">{r.dms_code || '-'}</td>
                      <td className="px-3 py-2 font-semibold text-on-surface">{r.outlet_name}</td>
                      <td className="px-3 py-2 text-on-surface-variant font-caption">{r.zone_name}</td>
                      <td className="px-3 py-2 text-on-surface-variant font-caption">{r.fos_name}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-primary">{formatCurrency(r.market_outstanding)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_lt_15)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_15_30)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_30_45)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_45_60)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface">{formatCurrency(r.bucket_60_75)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface">{formatCurrency(r.bucket_75_90)}</td>
                      <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-error">{formatCurrency(r.bucket_gt_90)}</td>
                      <td className="px-3 py-2 text-center">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold border ${
                            r.highest_overdue_bucket.includes('Critical')
                              ? 'bg-error-container text-on-error-container border-error'
                              : r.highest_overdue_bucket.includes('Severe')
                              ? 'bg-secondary-fixed text-on-secondary-fixed border-secondary-fixed-dim'
                              : 'bg-surface-container text-on-surface-variant border-outline-variant'
                          }`}
                        >
                          {r.highest_overdue_bucket}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* TAB 2: COLLECTIONS WORKBENCH */}
      {activeTab === 'collections_workbench' && (
        <CollectionsOverviewPage hideHeader />
      )}

      {/* TAB 3: OUTSTANDING & AGEING */}
      {activeTab === 'outstanding' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-headline-sm text-sm font-bold text-primary">Market Outstanding &amp; 7 Ageing Buckets</h3>
            <div className="flex items-center gap-2">
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
            </div>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Market Outstanding &amp; Ageing Buckets</CardTitle>
              <CardSubtitle>Accounts with open balances grouped across 7 overdue intervals</CardSubtitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-3 py-2 text-left font-bold text-primary">Brand</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">DMS Code</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Outlet Name</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Zone</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">FOS</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Market OS</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">&lt;15d</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">15-30d</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">30-45d</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">45-60d</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">60-75d</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">75-90d</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">&gt;90d</th>
                    <th className="px-3 py-2 text-center font-bold text-primary">Severity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest font-body-md">
                  {outstandingList.length === 0 ? (
                    <tr>
                      <td colSpan={14} className="text-center py-8 text-on-surface-variant font-caption">
                        No outstanding accounts found matching the current filters.
                      </td>
                    </tr>
                  ) : (
                    outstandingList.map((r, i) => (
                      <tr key={i} className="hover:bg-surface-container-low/70 transition-colors">
                        <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{r.brand}</td>
                        <td className="px-3 py-2 font-mono text-xs text-primary font-semibold">{r.dms_code || '-'}</td>
                        <td className="px-3 py-2 font-semibold text-on-surface">{r.outlet_name}</td>
                        <td className="px-3 py-2 text-on-surface-variant font-caption">{r.zone_name}</td>
                        <td className="px-3 py-2 text-on-surface-variant font-caption">{r.fos_name}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-primary">{formatCurrency(r.market_outstanding)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_lt_15)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_15_30)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_30_45)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{formatCurrency(r.bucket_45_60)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface">{formatCurrency(r.bucket_60_75)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface">{formatCurrency(r.bucket_75_90)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-error">{formatCurrency(r.bucket_gt_90)}</td>
                        <td className="px-3 py-2 text-center">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold border ${
                              r.highest_overdue_bucket.includes('Critical')
                                ? 'bg-error-container text-on-error-container border-error'
                                : r.highest_overdue_bucket.includes('Severe')
                                ? 'bg-secondary-fixed text-on-secondary-fixed border-secondary-fixed-dim'
                                : 'bg-surface-container text-on-surface-variant border-outline-variant'
                            }`}
                          >
                            {r.highest_overdue_bucket}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 4: OUTLETS DIRECTORY */}
      {activeTab === 'outlets' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-headline-sm text-sm font-bold text-primary">Outlets Master Directory (359 Outlets)</h3>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                icon={FileSpreadsheet}
                onClick={handleExportExcel}
                disabled={isLoading || isExporting}
              >
                Export Excel
              </Button>
            </div>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Outlets Master Directory</CardTitle>
              <CardSubtitle>Complete directory of 359 client outlets with coordinates and financial totals</CardSubtitle>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-3 py-2 text-left font-bold text-primary">DMS Code</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Outlet Name</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Zone</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Area</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Assigned FOS</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Location Status</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Sales</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Collections</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Market OS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest font-body-md">
                  {outletsList.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center py-8 text-on-surface-variant font-caption">
                        No outlets found matching query.
                      </td>
                    </tr>
                  ) : (
                    outletsList.map((o, i) => (
                      <tr key={i} className="hover:bg-surface-container-low/70 transition-colors">
                        <td className="px-3 py-2 font-mono text-xs text-primary font-bold">{o.dms_code || '-'}</td>
                        <td className="px-3 py-2 font-semibold text-on-surface">{o.outlet_name}</td>
                        <td className="px-3 py-2 text-on-surface-variant font-caption">{o.zone_name}</td>
                        <td className="px-3 py-2 text-on-surface-variant font-caption">{o.area_name}</td>
                        <td className="px-3 py-2 text-on-surface font-semibold">{o.fos_name}</td>
                        <td className="px-3 py-2">
                          <StatusBadge status={o.location_status} size="sm" />
                        </td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-primary">{formatCurrency(o.sales)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-primary">{formatCurrency(o.collection)}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-primary">{formatCurrency(o.market_outstanding)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 5: FIELD STAFF */}
      {activeTab === 'employees' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-headline-sm text-sm font-bold text-primary">
              Field Staff Performance ({employeeMasterList.length > 0 ? `${employeeMasterList.length} Real Field Staff` : 'All Officers'})
            </h3>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                icon={Download}
                onClick={() => exportCSV(employeeReport as any, 'employee-report')}
                disabled={employeeReport.length === 0}
              >
                Export CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                icon={Download}
                onClick={handleExportPDF}
                disabled={employeeReport.length === 0}
              >
                Export PDF
              </Button>
            </div>
          </div>

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-3 py-2 text-left font-bold text-primary">Employee ID</th>
                    <th className="px-3 py-2 text-left font-bold text-primary">Employee Name</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Total Visits</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Completed Visits</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Pending Visits</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Missed Visits</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Flagged Visits</th>
                    <th className="px-3 py-2 text-right font-bold text-primary">Completion Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest font-body-md">
                  {employeeReport.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center py-8 text-on-surface-variant font-caption">
                        No employees found matching the filter criteria.
                      </td>
                    </tr>
                  ) : (
                    employeeReport.map((e, i) => (
                      <tr key={i} className="hover:bg-surface-container-low/70 transition-colors">
                        <td className="px-3 py-2 font-mono text-xs text-primary font-bold">{e.employee_id}</td>
                        <td className="px-3 py-2 font-semibold text-on-surface">{e.employee_name}</td>
                        <td className="px-3 py-2 text-right text-on-surface">{e.total_visits}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-semibold text-primary">{e.completed_visits}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-on-surface-variant">{e.pending_visits}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-error">{e.missed_visits}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs text-secondary-container font-bold">{e.flagged_visits}</td>
                        <td className="px-3 py-2 text-right font-headline-sm text-xs font-bold text-primary">{e.completion_rate}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 6: VISITS & GPS AUDIT */}
      {activeTab === 'visits' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-container-highest pb-2">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => setVisitSubView('register')}
                className={`px-3 py-1.5 rounded-lg text-xs font-label-md uppercase tracking-wider font-semibold transition-all cursor-pointer ${
                  visitSubView === 'register'
                    ? 'bg-primary-container text-on-primary-container shadow-xs border border-primary-container'
                    : 'bg-surface border border-outline-variant text-on-surface-variant hover:text-on-surface hover:bg-surface-container'
                }`}
              >
                Operational Visits Register
              </button>
              <button
                onClick={() => setVisitSubView('geo')}
                className={`px-3 py-1.5 rounded-lg text-xs font-label-md uppercase tracking-wider font-semibold transition-all cursor-pointer ${
                  visitSubView === 'geo'
                    ? 'bg-primary-container text-on-primary-container shadow-xs border border-primary-container'
                    : 'bg-surface border border-outline-variant text-on-surface-variant hover:text-on-surface hover:bg-surface-container'
                }`}
              >
                Geo Verification Audit
              </button>
            </div>

            <div className="flex items-center gap-2">
              {visitSubView === 'register' ? (
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
                </>
              ) : (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    icon={Download}
                    onClick={() => exportCSV(geoReport as any, 'geo-verification-report')}
                    disabled={geoReport.length === 0}
                  >
                    Export CSV
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    icon={Download}
                    onClick={handleExportPDF}
                    disabled={geoReport.length === 0}
                  >
                    Export PDF
                  </Button>
                </>
              )}
            </div>
          </div>

          {visitSubView === 'register' ? (
            <Card>
              <CardHeader>
                <CardTitle>Operational Visits Register</CardTitle>
                <CardSubtitle>Field visits execution, check-in timestamps, and duration</CardSubtitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                    <tr>
                      <th className="px-3 py-2 text-left font-bold text-primary">Scheduled Date</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Employee</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Outlet</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">DMS Code</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Zone</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Status</th>
                      <th className="px-3 py-2 text-center font-bold text-primary">Check-In</th>
                      <th className="px-3 py-2 text-center font-bold text-primary">Check-Out</th>
                      <th className="px-3 py-2 text-right font-bold text-primary">Duration</th>
                      <th className="px-3 py-2 text-center font-bold text-primary">GPS</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest font-body-md">
                    {visitsList.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="text-center py-8 text-on-surface-variant font-caption">
                          No operational visits found for current date range.
                        </td>
                      </tr>
                    ) : (
                      visitsList.map((v, i) => (
                        <tr key={i} className="hover:bg-surface-container-low/70 transition-colors">
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{new Date(v.scheduled_at).toLocaleDateString()}</td>
                          <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{v.employee_name}</td>
                          <td className="px-3 py-2 text-on-surface">{v.customer_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-primary font-semibold">{v.dms_code || '-'}</td>
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{v.zone_name}</td>
                          <td className="px-3 py-2">
                            <StatusBadge status={v.status} size="sm" />
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-xs text-on-surface-variant">{v.check_in_at ? new Date(v.check_in_at).toLocaleTimeString() : '-'}</td>
                          <td className="px-3 py-2 text-center font-mono text-xs text-on-surface-variant">{v.check_out_at ? new Date(v.check_out_at).toLocaleTimeString() : '-'}</td>
                          <td className="px-3 py-2 text-right font-mono text-xs text-on-surface">{v.duration_minutes ? `${v.duration_minutes}m` : '-'}</td>
                          <td className="px-3 py-2 text-center">
                            <span className={`inline-block px-1.5 py-0.5 rounded font-label-md text-[10px] font-bold ${v.is_gps_verified ? 'bg-primary-tint text-primary' : 'text-outline'}`}>
                              {v.is_gps_verified ? 'YES' : 'NO'}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Geo Verification Audit</CardTitle>
                <CardSubtitle>Physical GPS distance deviation logs and validation checks</CardSubtitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                    <tr>
                      <th className="px-3 py-2 text-left font-bold text-primary">Attempt Time</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Employee</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Customer / Outlet</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Verification Type</th>
                      <th className="px-3 py-2 text-right font-bold text-primary">Distance (m)</th>
                      <th className="px-3 py-2 text-center font-bold text-primary">Status</th>
                      <th className="px-3 py-2 text-left font-bold text-primary">Failure Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest font-body-md">
                    {geoReport.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="text-center py-8 text-on-surface-variant font-caption">
                          No geo verification attempts recorded in selected range.
                        </td>
                      </tr>
                    ) : (
                      geoReport.map((g, i) => (
                        <tr key={i} className="hover:bg-surface-container-low/70 transition-colors">
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{new Date(g.attempted_at).toLocaleString()}</td>
                          <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{g.employee_name}</td>
                          <td className="px-3 py-2 text-on-surface">{g.customer_name}</td>
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{g.verification_type}</td>
                          <td className="px-3 py-2 text-right font-mono text-xs text-on-surface">{g.distance_m}m</td>
                          <td className="px-3 py-2 text-center">
                            <StatusBadge status={g.is_valid ? 'VALID' : 'INVALID'} size="sm" />
                          </td>
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{g.failure_reason || '-'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* TAB 10: PHASE 4 - MONTHLY REPORTS & HISTORICAL SNAPSHOTS */}
      {activeTab === 'monthly' && (
        <div className="space-y-6">
          <CardHeader className="px-0">
            <CardTitle className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-secondary-container" />
              Monthly Historical Reporting &amp; Finalization
            </CardTitle>
            <CardSubtitle>
              Historical monthly snapshots are archived and immutable once finalized by Admin.
            </CardSubtitle>
          </CardHeader>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {monthlyPeriods.map((period) => {
              const isLocked = period.status === 'FINALIZED';
              const mStr = `${period.period_year}-${String(period.period_month).padStart(2, '0')}`;
              const isCurrentSelected = selectedMonth === mStr;

              return (
                <Card
                  key={period.id}
                  variant={isCurrentSelected ? 'default' : 'hover'}
                  className={`p-5 transition-all ${
                    isCurrentSelected
                      ? 'border-2 border-primary-container bg-primary-tint/15 shadow-sm'
                      : ''
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-headline-sm text-base font-bold text-primary flex items-center gap-2">
                        {period.period_name}
                        {isLocked ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold bg-primary-container text-on-primary-container">
                            <Lock className="w-2.5 h-2.5" /> FINALIZED
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold bg-secondary-fixed text-on-secondary-fixed">
                            <Sparkles className="w-2.5 h-2.5 text-secondary-container" /> OPEN (LIVE)
                          </span>
                        )}
                      </h4>
                      <p className="font-caption text-xs text-on-surface-variant mt-1">
                        {period.snapshot_count} outlet snapshots recorded
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2.5 mt-4 pt-3 border-t border-surface-container-highest">
                    <div className="p-2 bg-surface-container-low rounded-lg border border-surface-container-highest">
                      <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">Total Sales</span>
                      <span className="font-headline-sm text-sm font-bold text-primary block">{formatCurrency(period.total_sales)}</span>
                    </div>
                    <div className="p-2 bg-surface-container-low rounded-lg border border-surface-container-highest">
                      <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">Collections</span>
                      <span className="font-headline-sm text-sm font-bold text-primary block">{formatCurrency(period.total_collection)}</span>
                    </div>
                    <div className="p-2 bg-surface-container-low rounded-lg border border-surface-container-highest">
                      <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">Market OS</span>
                      <span className="font-headline-sm text-sm font-bold text-primary block">{formatCurrency(period.total_market_os)}</span>
                    </div>
                    <div className="p-2 bg-surface-container-low rounded-lg border border-surface-container-highest">
                      <span className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant block mb-0.5">&gt;90d Overdue</span>
                      <span className="font-headline-sm text-sm font-bold text-error block">{formatCurrency(period.total_overdue_gt_90)}</span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between gap-2 mt-4 pt-3 border-t border-surface-container-highest">
                    <button
                      onClick={() => {
                        setSelectedMonth(mStr);
                        setActiveTab('business_bi');
                      }}
                      className="font-label-md text-xs uppercase tracking-wider font-semibold text-primary hover:text-secondary flex items-center gap-1 cursor-pointer transition-colors"
                    >
                      View BI <ArrowRight className="w-3 h-3 text-secondary-container" />
                    </button>

                    <div className="flex items-center gap-2">
                      {isLocked ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleReopenMonth(period)}
                          className="text-xs"
                        >
                          <Unlock className="w-3.5 h-3.5 mr-1" /> Reopen
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleFinalizeMonth(period)}
                          className="text-xs"
                        >
                          <Lock className="w-3.5 h-3.5 mr-1" /> Finalize Month
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

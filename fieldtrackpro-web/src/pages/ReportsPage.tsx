import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  CheckCircle2,
  TrendingUp,
  Users,
  Download,
  Calendar,
  Building2,
  Search,
  Lock,
  Unlock,
  Filter,
  RefreshCw,
  Clock,
  DollarSign,
  AlertTriangle,
  ArrowRight,
  Sparkles,
  X,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';
import { AppliedFiltersStrip } from '../components/reports/AppliedFiltersStrip';
import { ExportButtons, ExportFormat } from '../components/reports/ExportButtons';
import { useReportExport } from '../components/reports/useReportExport';
import { CollectionsOverviewPage } from './CollectionsOverviewPage';
import { apiClient } from '../api/client';
import { formatCalendarDate, formatIstDate, formatIstDateTime, formatIstTime } from '../utils/ist';
import {
  FILTER_TOOLTIP_NOT_APPLICABLE,
  FilterKey,
  MONTH_DISABLED_TOOLTIP,
  ReportFilterState,
  ReportTabId,
  VisitSubView,
  applicableFilters,
  buildReportRequest,
  describeAppliedFilters,
  tabSemanticsNotes,
} from '../utils/reportFilters';
import {
  BusinessBIDashboard,
  EmployeeReportRow,
  GeoReportRow,
  OutletReportRow,
  OutstandingAgeingReportRow,
  VisitDetailedReportRow,
  MonthlyReportingPeriod,
  MonthlyPeriodReviewSummary,
  Territory,
  Area,
  Employee,
  Brand,
} from '../types';
import { formatMoney as formatCurrency } from '../utils/money';

interface DateRange {
  startDate: string;
  endDate: string;
}

export type TabType = ReportTabId | 'business_bi';

const TAB_IDS: TabType[] = ['financial_bi', 'business_bi', 'collections_workbench', 'outstanding', 'outlets', 'employees', 'visits', 'monthly'];

const SEARCH_DEBOUNCE_MS = 350;

const CONTROL_CLASS =
  'w-full h-9 bg-surface border border-outline-variant rounded-lg px-2.5 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-surface-container-low';

export const ReportsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get('tab') as TabType | null;
  const initialTab: TabType = rawTab && TAB_IDS.includes(rawTab)
    ? (rawTab === 'business_bi' ? 'financial_bi' : rawTab)
    : 'financial_bi';

  // Navigation State
  const [activeTab, setActiveTab] = useState<TabType>(initialTab);
  const [biSubTab, setBiSubTab] = useState<'brand' | 'zone' | 'area' | 'fos' | 'raw'>('brand');
  const [visitSubView, setVisitSubView] = useState<VisitSubView>('register');
  const tabId: ReportTabId = activeTab === 'business_bi' ? 'financial_bi' : activeTab;

  useEffect(() => {
    const tabParam = searchParams.get('tab') as TabType;
    if (tabParam && TAB_IDS.includes(tabParam)) {
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
  const [collectionStatus, setCollectionStatus] = useState<string>('');
  const [visitStatus, setVisitStatus] = useState<string>('ALL');
  const [locationStatus, setLocationStatus] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [debouncedSearch, setDebouncedSearch] = useState<string>('');
  const [dateRange, setDateRange] = useState<DateRange>({ startDate: '', endDate: '' });
  const [appliedDateRange, setAppliedDateRange] = useState<DateRange>({ startDate: '', endDate: '' });
  const [dateError, setDateError] = useState<string | null>(null);

  // Typing in the search box refetches after a short pause (not on every keystroke).
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchQuery]);

  // Master Data Options for Filters
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [employeeOptions, setEmployeeOptions] = useState<Employee[]>([]);
  const [monthlyPeriods, setMonthlyPeriods] = useState<MonthlyReportingPeriod[]>([]);
  const [masterBrands, setMasterBrands] = useState<Brand[]>([]);

  // Authoritative Tally transaction months: only show periods that have real data
  const availablePeriodsWithData = useMemo(() => {
    return monthlyPeriods.filter(
      (p) =>
        Number(p.total_sales) > 0 ||
        Number(p.total_collection) > 0 ||
        (p.snapshot_count ?? 0) > 0 ||
        (p.total_outlets ?? 0) > 0
    );
  }, [monthlyPeriods]);

  // Report Datasets
  const [businessBI, setBusinessBI] = useState<BusinessBIDashboard | null>(null);
  const [employeeReport, setEmployeeReport] = useState<EmployeeReportRow[]>([]);
  const [outletsList, setOutletsList] = useState<OutletReportRow[]>([]);
  const [outstandingList, setOutstandingList] = useState<OutstandingAgeingReportRow[]>([]);
  const [visitsList, setVisitsList] = useState<VisitDetailedReportRow[]>([]);
  const [geoReport, setGeoReport] = useState<GeoReportRow[]>([]);

  // Status & Async State
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const { exporting, run: runExport } = useReportExport(
    (message) => setError(message),
    (filename) => {
      setActionSuccess(`Exported ${filename}`);
      setTimeout(() => setActionSuccess(null), 4000);
    },
  );

  // Load Reference Data (Territories, Areas, Employees, Monthly Periods)
  useEffect(() => {
    const loadMasters = async () => {
      try {
        const [tList, aList, eList, pList, bList] = await Promise.all([
          apiClient.getTerritories().catch(() => [] as Territory[]),
          apiClient.getAreas().catch(() => [] as Area[]),
          apiClient.getEmployees().catch(() => [] as Employee[]),
          apiClient.getMonthlyPeriods().catch(() => [] as MonthlyReportingPeriod[]),
          apiClient.getBrands(true).catch(() => [] as Brand[]),
        ]);
        setTerritories(tList || []);
        setAreas(aList || []);
        setEmployeeOptions(eList || []);
        setMonthlyPeriods(pList || []);
        setMasterBrands(bList || []);
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

  // ---------------------------------------------------------------------------
  // The ONE request per tab: the same (report, params) pair loads the table and
  // is sent to the export endpoint, and the "Applied filters" strip is derived
  // from it - so nothing can be shown that was not applied.
  // ---------------------------------------------------------------------------
  const filters: ReportFilterState = useMemo(
    () => ({
      month: selectedMonth,
      brand: selectedBrand,
      zoneId: selectedZoneId,
      areaId: selectedAreaId,
      employeeId: selectedEmployeeId,
      ageingBucket: selectedAgeingBucket,
      search: debouncedSearch,
      startDate: appliedDateRange.startDate,
      endDate: appliedDateRange.endDate,
      collectionStatus,
      visitStatus,
      locationStatus,
    }),
    [
      selectedMonth, selectedBrand, selectedZoneId, selectedAreaId, selectedEmployeeId, selectedAgeingBucket,
      debouncedSearch, appliedDateRange, collectionStatus, visitStatus, locationStatus,
    ],
  );
  const request = useMemo(() => buildReportRequest(tabId, filters, visitSubView), [tabId, filters, visitSubView]);
  const requestKey = JSON.stringify(request);
  const applies = useMemo(() => new Set<FilterKey>(applicableFilters(tabId, visitSubView)), [tabId, visitSubView]);
  const hasDates = !!appliedDateRange.startDate || !!appliedDateRange.endDate;

  const loadSeq = useRef(0);

  // Main Data Loader based on Active Tab and the tab's request
  const loadActiveReport = useCallback(async () => {
    const seq = ++loadSeq.current;
    const req = JSON.parse(requestKey) as typeof request;
    setIsLoading(true);
    setError(null);
    try {
      switch (req.report) {
        case 'business_summary':
          setBusinessBI(await apiClient.getReport<BusinessBIDashboard>('business_summary', req.params));
          break;
        case 'outstanding':
          setOutstandingList(await apiClient.getReport<OutstandingAgeingReportRow[]>('outstanding', req.params));
          break;
        case 'outlets':
          setOutletsList(await apiClient.getReport<OutletReportRow[]>('outlets', req.params));
          break;
        case 'staff':
          setEmployeeReport(await apiClient.getReport<EmployeeReportRow[]>('staff', req.params));
          break;
        case 'visits':
          setVisitsList(await apiClient.getReport<VisitDetailedReportRow[]>('visits', req.params));
          break;
        case 'geo':
          setGeoReport(await apiClient.getReport<GeoReportRow[]>('geo', req.params));
          break;
        default:
          break; // monthly periods are loaded once with the master data; the collections tab loads itself
      }
    } catch (err) {
      if (seq !== loadSeq.current) return;
      // A failed request must not masquerade as an empty report.
      const message = err instanceof Error ? err.message : 'Failed to load report';
      setError(`Could not load this report: ${message}. The figures shown may be incomplete.`);
    } finally {
      if (seq === loadSeq.current) setIsLoading(false);
    }
  }, [requestKey]);

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
    setCollectionStatus('');
    setVisitStatus('ALL');
    setLocationStatus('ALL');
    setSearchQuery('');
    setDebouncedSearch('');
    clearDateFilter();
  };

  // ---------------------------------------------------------------------------
  // Export Handlers (server-side Excel / PDF, ALL filtered rows)
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

  const handleExport = (format: ExportFormat) => {
    // Same request as the table; the PDF of the BI tab prints the selected summary view.
    const extra = request.report === 'business_summary' && format === 'pdf' ? { view: biSubTab } : undefined;
    void runExport(request, format, extra);
  };

  const rowCount: Record<ReportTabId, number> = {
    financial_bi: businessBI?.raw_outlet_rows.length ?? 0,
    collections_workbench: 1, // the Collections tab owns its own export buttons
    outstanding: outstandingList.length,
    outlets: outletsList.length,
    employees: employeeReport.length,
    visits: visitSubView === 'geo' ? geoReport.length : visitsList.length,
    monthly: availablePeriodsWithData.length,
  };
  const exportButtons = (extra?: React.ReactNode) => (
    <ExportButtons
      onExport={handleExport}
      exporting={exporting}
      loading={isLoading}
      empty={rowCount[tabId] === 0}
      emptyReason="No rows match the current filters - nothing to export"
    >
      {extra}
    </ExportButtons>
  );

  // Monthly Period Review & Reopen Modal States
  const [reviewPeriod, setReviewPeriod] = useState<MonthlyReportingPeriod | null>(null);
  const [reviewSummary, setReviewSummary] = useState<MonthlyPeriodReviewSummary | null>(null);
  const [isReviewLoading, setIsReviewLoading] = useState<boolean>(false);
  const [isFinalizingPeriod, setIsFinalizingPeriod] = useState<boolean>(false);

  const [reopenTargetPeriod, setReopenTargetPeriod] = useState<MonthlyReportingPeriod | null>(null);
  const [reopenReasonText, setReopenReasonText] = useState<string>('');
  const [reopenError, setReopenError] = useState<string | null>(null);
  const [isReopeningPeriod, setIsReopeningPeriod] = useState<boolean>(false);

  const handleOpenPeriodReview = async (period: MonthlyReportingPeriod) => {
    setReviewPeriod(period);
    setIsReviewLoading(true);
    try {
      const summary = await apiClient.getMonthlyPeriodReview(period.id);
      setReviewSummary(summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load period review');
    } finally {
      setIsReviewLoading(false);
    }
  };

  const handleConfirmFinalizeMonth = async () => {
    if (!reviewPeriod) return;
    setIsFinalizingPeriod(true);
    try {
      const updated = await apiClient.finalizeMonthlyPeriod(reviewPeriod.id);
      setMonthlyPeriods((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionSuccess(`Monthly period ${reviewPeriod.period_name} finalized and locked successfully.`);
      setReviewPeriod(null);
      setReviewSummary(null);
      setTimeout(() => setActionSuccess(null), 4000);
      loadActiveReport();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to finalize month');
    } finally {
      setIsFinalizingPeriod(false);
    }
  };

  const handleOpenReopenModal = (period: MonthlyReportingPeriod) => {
    setReopenTargetPeriod(period);
    setReopenReasonText('');
    setReopenError(null);
  };

  const handleConfirmReopenMonth = async () => {
    if (!reopenTargetPeriod) return;
    const cleanReason = reopenReasonText.trim();
    if (!cleanReason) {
      setReopenError('Please provide an administrative reason for reopening this period.');
      return;
    }
    setIsReopeningPeriod(true);
    setReopenError(null);
    try {
      const updated = await apiClient.reopenMonthlyPeriod(reopenTargetPeriod.id, cleanReason);
      setMonthlyPeriods((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionSuccess(`Monthly period ${reopenTargetPeriod.period_name} reopened.`);
      setReopenTargetPeriod(null);
      setReopenReasonText('');
      setTimeout(() => setActionSuccess(null), 4000);
      loadActiveReport();
    } catch (err) {
      setReopenError(err instanceof Error ? err.message : 'Failed to reopen month');
    } finally {
      setIsReopeningPeriod(false);
    }
  };

  const na = (key: FilterKey) => !applies.has(key);
  const tip = (key: FilterKey) => (na(key) ? FILTER_TOOLTIP_NOT_APPLICABLE : undefined);
  const appliedItems = describeAppliedFilters(request, {
    zones: territories,
    areas,
    employees: employeeOptions,
  });
  const semanticsNotes = tabSemanticsNotes(tabId, filters, visitSubView);

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

      {/* Global Filter Engine - one bar, every control either applies to the active tab or is disabled with a reason */}
      {tabId !== 'monthly' ? (
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
              <div title={na('month') ? FILTER_TOOLTIP_NOT_APPLICABLE : hasDates ? MONTH_DISABLED_TOOLTIP : undefined}>
                <label htmlFor="rf-month" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Month Period
                </label>
                <select
                  id="rf-month"
                  className={CONTROL_CLASS}
                  value={selectedMonth}
                  disabled={na('month') || hasDates}
                  onChange={(e) => setSelectedMonth(e.target.value)}
                >
                  <option value="ALL">All Available Months</option>
                  {availablePeriodsWithData.map((p) => {
                    const mStr = `${p.period_year}-${String(p.period_month).padStart(2, '0')}`;
                    const tag = p.status === 'FINALIZED' ? '🔒 (Locked)' : p.status === 'PENDING_CLOSE' ? '⏳ (Pending Close)' : '🟢 (Current)';
                    return (
                      <option key={p.id} value={mStr}>
                        {p.period_name} {tag}
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Brand Filter */}
              <div title={tip('brand')}>
                <label htmlFor="rf-brand" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Brand
                </label>
                <select
                  id="rf-brand"
                  className={CONTROL_CLASS}
                  value={selectedBrand}
                  disabled={na('brand')}
                  onChange={(e) => setSelectedBrand(e.target.value)}
                >
                  <option value="ALL">All Brands</option>
                  {masterBrands.map((b) => (
                    <option key={b.id} value={b.name}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Zone Filter */}
              <div title={tip('zone')}>
                <label htmlFor="rf-zone" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Zone (Territory)
                </label>
                <select
                  id="rf-zone"
                  className={CONTROL_CLASS}
                  value={selectedZoneId}
                  disabled={na('zone')}
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
              <div title={tip('area')}>
                <label htmlFor="rf-area" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Area
                </label>
                <select
                  id="rf-area"
                  className={CONTROL_CLASS}
                  value={selectedAreaId}
                  disabled={na('area')}
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
              <div title={tip('employee')}>
                <label htmlFor="rf-employee" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  FOS / Field Officer
                </label>
                <select
                  id="rf-employee"
                  className={CONTROL_CLASS}
                  value={selectedEmployeeId}
                  disabled={na('employee')}
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

              {/* Ageing Bucket Filter (snapshot buckets - Outstanding tab only) */}
              <div title={tip('ageing')}>
                <label htmlFor="rf-ageing" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                  Ageing Bucket
                </label>
                <select
                  id="rf-ageing"
                  className={CONTROL_CLASS}
                  value={selectedAgeingBucket}
                  disabled={na('ageing')}
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

              {/* Tab specific selects */}
              {applies.has('collectionStatus') && (
                <div>
                  <label htmlFor="rf-collection-status" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                    Collection Status
                  </label>
                  <select
                    id="rf-collection-status"
                    className={CONTROL_CLASS}
                    value={collectionStatus}
                    onChange={(e) => setCollectionStatus(e.target.value)}
                  >
                    <option value="">All Statuses</option>
                    <option value="NORMAL">Current / Not Due</option>
                    <option value="WARNING">Warning (21-25 days)</option>
                    <option value="OVERDUE">Overdue (26+ days)</option>
                    <option value="PAID">Paid</option>
                  </select>
                </div>
              )}
              {applies.has('visitStatus') && (
                <div>
                  <label htmlFor="rf-visit-status" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                    Visit Status
                  </label>
                  <select
                    id="rf-visit-status"
                    className={CONTROL_CLASS}
                    value={visitStatus}
                    onChange={(e) => setVisitStatus(e.target.value)}
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="PENDING">Pending</option>
                    <option value="IN_PROGRESS">In progress</option>
                    <option value="COMPLETED">Completed</option>
                    <option value="MISSED">Missed</option>
                    <option value="FLAGGED">Flagged</option>
                  </select>
                </div>
              )}
              {applies.has('locationStatus') && (
                <div>
                  <label htmlFor="rf-location-status" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
                    Location Status
                  </label>
                  <select
                    id="rf-location-status"
                    className={CONTROL_CLASS}
                    value={locationStatus}
                    onChange={(e) => setLocationStatus(e.target.value)}
                  >
                    <option value="ALL">All</option>
                    <option value="VERIFIED">Verified</option>
                    <option value="PENDING">Pending</option>
                    <option value="MISSING">Missing</option>
                  </select>
                </div>
              )}
            </div>

            {/* Search bar & Date Filter */}
            <div className="pt-2 border-t border-surface-container-highest flex flex-wrap items-center justify-between gap-3">
              <div className="relative flex-1 min-w-[200px] max-w-sm" title={tip('search')}>
                <Search className="w-3.5 h-3.5 absolute left-3 top-3 text-on-surface-variant" />
                <input
                  type="text"
                  aria-label="Search"
                  placeholder="Search DMS code, outlet, or officer..."
                  value={searchQuery}
                  disabled={na('search')}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full h-9 bg-surface border border-outline-variant rounded-lg pl-8 pr-3 py-1.5 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                />
              </div>

              <div className="flex flex-wrap items-center gap-2" title={tip('dates')}>
                <span className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold">Date Range (IST):</span>
                <input
                  type="date"
                  aria-label="Start date"
                  value={dateRange.startDate}
                  disabled={na('dates')}
                  onChange={(e) => handleDateChange('startDate', e.target.value)}
                  className="h-8 bg-surface border border-outline-variant rounded-md px-2 py-1 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container disabled:opacity-50"
                />
                <span className="text-on-surface-variant text-xs font-caption">to</span>
                <input
                  type="date"
                  aria-label="End date"
                  value={dateRange.endDate}
                  disabled={na('dates')}
                  onChange={(e) => handleDateChange('endDate', e.target.value)}
                  className="h-8 bg-surface border border-outline-variant rounded-md px-2 py-1 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container disabled:opacity-50"
                />
                <Button size="sm" variant="secondary" onClick={applyDateFilter} disabled={na('dates')} className="h-8 text-xs py-1">
                  Apply Filter
                </Button>
                <Button size="sm" variant="outline" onClick={clearDateFilter} disabled={na('dates')} className="h-8 text-xs py-1">
                  Clear
                </Button>
              </div>
            </div>

            {/* Date Error */}
            {dateError && (
              <p className="text-xs text-error font-medium pt-1">{dateError}</p>
            )}

            {/* Applied filters - derived from the exact params sent for this tab */}
            <AppliedFiltersStrip items={appliedItems} notes={semanticsNotes} />
          </div>
        </Card>
      ) : (
        <AppliedFiltersStrip items={[]} notes={semanticsNotes} />
      )}

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
            <div className="flex flex-wrap items-center gap-3">
              {businessBI && (
                <div className="font-caption text-xs text-on-surface-variant" data-testid="bi-totals">
                  Total Outlets: <span className="font-semibold text-primary">{businessBI.total_outlets}</span> | Total OS: <span className="font-semibold text-primary font-headline-sm">{formatCurrency(businessBI.total_market_outstanding)}</span>
                  {businessBI.as_of_date && businessBI.data_source !== 'LIVE_INVOICES' ? (
                    <span data-testid="bi-as-of"> (as of {formatCalendarDate(businessBI.as_of_date)})</span>
                  ) : null}
                </div>
              )}
              {exportButtons()}
            </div>
          </div>

          {businessBI?.data_source === 'LIVE_INVOICES' && (
            <div
              role="status"
              data-testid="bi-live-note"
              className="p-3 rounded-xl bg-amber-50 border border-amber-300 text-amber-900 text-xs flex items-start gap-2"
            >
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>
                <strong>Live invoices, not a snapshot.</strong> {businessBI.data_source_note}
              </span>
            </div>
          )}

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

      {/* TAB 2: COLLECTIONS WORKBENCH */}
      {activeTab === 'collections_workbench' && (
        <CollectionsOverviewPage hideHeader externalRequest={request} />
      )}

      {/* TAB 3: OUTSTANDING & AGEING */}
      {activeTab === 'outstanding' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-headline-sm text-sm font-bold text-primary">Market Outstanding &amp; 7 Ageing Buckets</h3>
            {exportButtons()}
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Market Outstanding &amp; Ageing Buckets</CardTitle>
              <CardSubtitle>Accounts with open balances grouped across 7 overdue intervals (latest snapshot in the period, as of the date shown)</CardSubtitle>
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
                    <th className="px-3 py-2 text-center font-bold text-primary">As of</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest font-body-md">
                  {outstandingList.length === 0 ? (
                    <tr>
                      <td colSpan={15} className="text-center py-8 text-on-surface-variant font-caption">
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
                        <td className="px-3 py-2 text-center text-on-surface-variant font-caption">{formatCalendarDate(r.as_of_date)}</td>
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
            <h3 className="font-headline-sm text-sm font-bold text-primary">Outlets Master Directory ({outletsList.length} Outlets)</h3>
            {exportButtons()}
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Outlets Master Directory</CardTitle>
              <CardSubtitle>Directory of {outletsList.length} client outlets (one row each) with financial totals for the selected period; market OS is the latest snapshot per brand</CardSubtitle>
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
                    <th className="px-3 py-2 text-center font-bold text-primary">As of</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest font-body-md">
                  {outletsList.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="text-center py-8 text-on-surface-variant font-caption">
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
                        <td className="px-3 py-2 text-center text-on-surface-variant font-caption">{formatCalendarDate(o.as_of_date)}</td>
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
              Field Staff Performance ({employeeReport.length} {employeeReport.length === 1 ? 'officer' : 'officers'})
            </h3>
            {exportButtons(
              <Button
                variant="outline"
                size="sm"
                icon={Download}
                onClick={() =>
                  exportCSV(
                    employeeReport.map((e) => ({
                      employee_code: e.employee_code ?? '',
                      employee_name: e.employee_name,
                      total_visits: e.total_visits,
                      completed_visits: e.completed_visits,
                      pending_visits: e.pending_visits,
                      missed_visits: e.missed_visits,
                      flagged_visits: e.flagged_visits,
                      completion_rate: e.completion_rate,
                    })),
                    'employee-report',
                  )
                }
                disabled={employeeReport.length === 0}
              >
                Export CSV
              </Button>,
            )}
          </div>

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-3 py-2 text-left font-bold text-primary">Employee Code</th>
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
                        <td className="px-3 py-2 font-mono text-xs text-primary font-bold">{e.employee_code || '-'}</td>
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

            {exportButtons(
              visitSubView === 'geo' ? (
                <Button
                  variant="outline"
                  size="sm"
                  icon={Download}
                  onClick={() => exportCSV(geoReport as unknown as Record<string, unknown>[], 'geo-verification-report')}
                  disabled={geoReport.length === 0}
                >
                  Export CSV
                </Button>
              ) : null,
            )}
          </div>

          {visitSubView === 'register' ? (
            <Card>
              <CardHeader>
                <CardTitle>Operational Visits Register</CardTitle>
                <CardSubtitle>Field visits execution, check-in timestamps, and duration (all dates and times are IST)</CardSubtitle>
              </CardHeader>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase text-[10px] tracking-wider border-b border-surface-container-highest">
                    <tr>
                      <th className="px-3 py-2 text-left font-bold text-primary">Scheduled Date (IST)</th>
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
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{formatIstDate(v.scheduled_at)}</td>
                          <td className="px-3 py-2 font-headline-sm text-xs font-bold text-primary">{v.employee_name}</td>
                          <td className="px-3 py-2 text-on-surface">{v.customer_name}</td>
                          <td className="px-3 py-2 font-mono text-xs text-primary font-semibold">{v.dms_code || '-'}</td>
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{v.zone_name}</td>
                          <td className="px-3 py-2">
                            <StatusBadge status={v.status} size="sm" />
                          </td>
                          <td className="px-3 py-2 text-center font-mono text-xs text-on-surface-variant">{v.check_in_at ? formatIstTime(v.check_in_at) : '-'}</td>
                          <td className="px-3 py-2 text-center font-mono text-xs text-on-surface-variant">{v.check_out_at ? formatIstTime(v.check_out_at) : '-'}</td>
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
                      <th className="px-3 py-2 text-left font-bold text-primary">Attempt Time (IST)</th>
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
                          <td className="px-3 py-2 text-on-surface-variant font-caption">{formatIstDateTime(g.attempted_at)}</td>
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
          <div className="flex flex-wrap items-start justify-between gap-3">
            <CardHeader className="px-0">
              <CardTitle className="flex items-center gap-2">
                <Calendar className="w-5 h-5 text-secondary-container" />
                Monthly Accounting Periods &amp; Finalization
              </CardTitle>
              <CardSubtitle>
                Historical monthly snapshots and accounting ledgers are protected and immutable once locked by Admin.
              </CardSubtitle>
            </CardHeader>
            {exportButtons()}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {availablePeriodsWithData.map((period) => {
              const isLocked = period.status === 'FINALIZED';
              const isPending = period.status === 'PENDING_CLOSE';
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
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-300 border border-slate-300 dark:border-slate-700">
                            <Lock className="w-2.5 h-2.5" /> LOCKED
                          </span>
                        ) : isPending ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-700">
                            <Clock className="w-2.5 h-2.5" /> PENDING CLOSE
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label-md text-[10px] uppercase tracking-wider font-semibold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700">
                            <Sparkles className="w-2.5 h-2.5" /> CURRENT / OPEN
                          </span>
                        )}
                      </h4>
                      <p className="font-caption text-xs text-on-surface-variant mt-1">
                        {period.snapshot_count} outlet snapshots archived
                      </p>
                      {period.finalized_at && (
                        <p className="text-[10px] text-on-surface-variant mt-0.5">
                          Locked: {new Date(period.finalized_at).toLocaleDateString()}
                        </p>
                      )}
                      {period.reopen_reason && (
                        <p className="text-[10px] text-amber-700 dark:text-amber-400 mt-0.5 italic">
                          Reopen Reason: &quot;{period.reopen_reason}&quot;
                        </p>
                      )}
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
                        clearDateFilter(); // an applied date range would override the month
                        handleTabChange('financial_bi');
                      }}
                      className="font-label-md text-xs uppercase tracking-wider font-semibold text-primary hover:text-secondary flex items-center gap-1 cursor-pointer transition-colors"
                    >
                      View BI <ArrowRight className="w-3 h-3 text-secondary-container" />
                    </button>

                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleOpenPeriodReview(period)}
                        className="text-xs"
                      >
                        Review
                      </Button>
                      {isLocked ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleOpenReopenModal(period)}
                          className="text-xs"
                        >
                          <Unlock className="w-3.5 h-3.5 mr-1" /> Reopen
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleOpenPeriodReview(period)}
                          className="text-xs"
                        >
                          <Lock className="w-3.5 h-3.5 mr-1" /> Close &amp; Lock
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

      {/* Review Modal */}
      {reviewPeriod && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-scrim/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-surface rounded-2xl border border-outline-variant/60 shadow-xl max-w-xl w-full p-6 space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-outline-variant/40">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-primary/10 text-primary rounded-lg">
                  <Lock className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-headline-sm text-base font-bold text-on-surface">
                    {reviewPeriod.period_name} — Month Close Review
                  </h3>
                  <span className="font-caption text-xs text-on-surface-variant">
                    Review operational and financial aggregates before locking the accounting period.
                  </span>
                </div>
              </div>
              <button
                onClick={() => {
                  setReviewPeriod(null);
                  setReviewSummary(null);
                }}
                className="p-1 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {isReviewLoading ? (
              <div className="py-8 text-center text-on-surface-variant text-sm flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-primary" />
                Loading period review summary...
              </div>
            ) : reviewSummary ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div className="p-3 bg-surface-container-low rounded-xl border border-outline-variant/30 text-center">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-on-surface-variant block">Completed Visits</span>
                    <p className="text-base font-bold text-primary mt-1">{reviewSummary.visits_completed}</p>
                    <span className="text-[10px] text-on-surface-variant">{reviewSummary.visits_adhoc} ad-hoc</span>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl border border-outline-variant/30 text-center">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-on-surface-variant block">Collections</span>
                    <p className="text-base font-bold text-emerald-600 mt-1">{formatCurrency(reviewSummary.collections_submitted_amount)}</p>
                    <span className="text-[10px] text-on-surface-variant">{formatCurrency(reviewSummary.collections_verified_amount)} verified</span>
                  </div>
                  <div className="p-3 bg-surface-container-low rounded-xl border border-outline-variant/30 text-center">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-on-surface-variant block">Market Outstanding</span>
                    <p className="text-base font-bold text-amber-600 mt-1">{formatCurrency(reviewSummary.total_outstanding)}</p>
                    <span className="text-[10px] text-on-surface-variant">{reviewSummary.total_invoices_count} invoices</span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs text-on-surface space-y-1.5">
                  <p className="font-bold flex items-center gap-1 text-amber-800 dark:text-amber-300">
                    <AlertTriangle className="w-4 h-4 text-amber-600" />
                    Important Financial Lock Notice:
                  </p>
                  <p className="text-on-surface-variant leading-relaxed">
                    After closing <strong>{reviewPeriod.period_name}</strong>, new financial transactions (collections, invoices) cannot be backdated into this month. Any future payments collected for {reviewPeriod.period_name} invoices will be recorded in the open month.
                  </p>
                </div>
              </div>
            ) : null}

            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-outline-variant/40">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setReviewPeriod(null);
                  setReviewSummary(null);
                }}
                disabled={isFinalizingPeriod}
              >
                Cancel
              </Button>
              {reviewPeriod.status !== 'FINALIZED' && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Lock}
                  onClick={handleConfirmFinalizeMonth}
                  isLoading={isFinalizingPeriod}
                  disabled={isReviewLoading}
                >
                  Close &amp; Lock {reviewPeriod.period_name}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Controlled Reopen Modal */}
      {reopenTargetPeriod && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-scrim/60 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="bg-surface rounded-2xl border border-outline-variant/60 shadow-xl max-w-lg w-full p-6 space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between pb-3 border-b border-outline-variant/40">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-amber-500/10 text-amber-600 rounded-lg">
                  <Unlock className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-headline-sm text-base font-bold text-on-surface">
                    Reopen {reopenTargetPeriod.period_name}
                  </h3>
                  <span className="font-caption text-xs text-on-surface-variant">
                    Admin Authorization &amp; Reason Required
                  </span>
                </div>
              </div>
              <button
                onClick={() => setReopenTargetPeriod(null)}
                className="p-1 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {reopenError && <ErrorBanner message={reopenError} onDismiss={() => setReopenError(null)} />}

            <div className="space-y-2">
              <label className="text-xs font-bold text-on-surface block">
                Reason for Reopening Period <span className="text-error">*</span>
              </label>
              <textarea
                value={reopenReasonText}
                onChange={(e) => setReopenReasonText(e.target.value)}
                placeholder="E.g., Auditor request to settle dispute on invoice INV-2026-881..."
                rows={3}
                className="w-full bg-surface border border-outline-variant rounded-xl p-3 text-xs text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
              />
              <span className="text-[11px] text-on-surface-variant block">
                This action and the supplied reason will be stamped in the audit trail.
              </span>
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-outline-variant/40">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setReopenTargetPeriod(null)}
                disabled={isReopeningPeriod}
              >
                Cancel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={Unlock}
                onClick={handleConfirmReopenMonth}
                isLoading={isReopeningPeriod}
                disabled={!reopenReasonText.trim()}
              >
                Confirm &amp; Reopen
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

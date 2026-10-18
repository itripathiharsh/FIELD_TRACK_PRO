/**
 * Single source of truth for the Reports & Collections filter bar:
 *   - which filters apply to which tab (nothing is a silent no-op),
 *   - the exact query params sent to the API (used for BOTH loading and exporting),
 *   - the "Applied filters" summary, derived from those very params.
 */
import { Area, Employee, Territory } from '../types';
import { formatCalendarDate, formatMonthLabel } from './ist';

export type ReportTabId =
  | 'financial_bi'
  | 'collections_workbench'
  | 'outstanding'
  | 'outlets'
  | 'employees'
  | 'visits'
  | 'monthly';

export type VisitSubView = 'register' | 'geo';

export type FilterKey =
  | 'month'
  | 'dates'
  | 'brand'
  | 'zone'
  | 'area'
  | 'employee'
  | 'ageing'
  | 'search'
  | 'collectionStatus'
  | 'visitStatus'
  | 'locationStatus';

export interface ReportFilterState {
  month: string; // 'ALL' or YYYY-MM
  brand: string; // 'ALL' or name
  zoneId: string; // 'ALL' or id
  areaId: string;
  employeeId: string;
  ageingBucket: string;
  search: string;
  startDate: string; // applied dates, '' = unset
  endDate: string;
  collectionStatus: string; // '' = all
  visitStatus: string; // 'ALL' or status
  locationStatus: string; // 'ALL' or status
}

export const emptyReportFilters: ReportFilterState = {
  month: 'ALL',
  brand: 'ALL',
  zoneId: 'ALL',
  areaId: 'ALL',
  employeeId: 'ALL',
  ageingBucket: 'ALL',
  search: '',
  startDate: '',
  endDate: '',
  collectionStatus: '',
  visitStatus: 'ALL',
  locationStatus: 'ALL',
};

/** The filters that actually change the data on each tab (everything else is disabled in the UI). */
export function applicableFilters(tab: ReportTabId, visitSubView: VisitSubView = 'register'): FilterKey[] {
  switch (tab) {
    case 'financial_bi':
      return ['month', 'dates', 'brand', 'zone', 'area', 'employee'];
    case 'collections_workbench':
      return ['dates', 'zone', 'area', 'employee', 'collectionStatus', 'search'];
    case 'outstanding':
      return ['month', 'dates', 'brand', 'zone', 'area', 'employee', 'ageing', 'search'];
    case 'outlets':
      return ['month', 'dates', 'brand', 'zone', 'area', 'employee', 'locationStatus', 'search'];
    case 'employees':
      return ['dates', 'zone', 'area', 'employee', 'search'];
    case 'visits':
      return visitSubView === 'geo'
        ? ['dates', 'zone', 'area', 'employee', 'search']
        : ['dates', 'zone', 'area', 'employee', 'visitStatus', 'search'];
    case 'monthly':
    default:
      return [];
  }
}

export const FILTER_TOOLTIP_NOT_APPLICABLE = 'Not used by this tab - it would not change these figures.';
export const MONTH_DISABLED_TOOLTIP = 'A date range is applied, so the month is ignored. Clear the dates to use the month.';

export type ReportKey =
  | 'business_summary'
  | 'outstanding'
  | 'outlets'
  | 'visits'
  | 'geo'
  | 'staff'
  | 'collections_overview'
  | 'monthly_periods';

export const REPORT_ENDPOINTS: Record<ReportKey, string> = {
  business_summary: '/api/v1/reports/business-summary',
  outstanding: '/api/v1/reports/outstanding',
  outlets: '/api/v1/reports/outlets',
  visits: '/api/v1/reports/visits-detailed',
  geo: '/api/v1/reports/geo-verification',
  staff: '/api/v1/reports/employees',
  collections_overview: '/api/v1/collections/overview',
  monthly_periods: '/api/v1/reports/monthly-periods',
};

export type ReportParams = Record<string, string>;

export interface ReportRequest {
  report: ReportKey;
  params: ReportParams;
}

const isSet = (v: string | undefined | null): v is string => !!v && v !== 'ALL';

export function reportForTab(tab: ReportTabId, visitSubView: VisitSubView = 'register'): ReportKey {
  switch (tab) {
    case 'financial_bi':
      return 'business_summary';
    case 'collections_workbench':
      return 'collections_overview';
    case 'outstanding':
      return 'outstanding';
    case 'outlets':
      return 'outlets';
    case 'employees':
      return 'staff';
    case 'visits':
      return visitSubView === 'geo' ? 'geo' : 'visits';
    case 'monthly':
    default:
      return 'monthly_periods';
  }
}

/**
 * The exact params for a tab: only filters that apply to it are included, and
 * `month` is dropped when a date range is applied (the range wins).
 */
export function buildReportRequest(
  tab: ReportTabId,
  f: ReportFilterState,
  visitSubView: VisitSubView = 'register',
): ReportRequest {
  const report = reportForTab(tab, visitSubView);
  const applies = new Set(applicableFilters(tab, visitSubView));
  const p: ReportParams = {};
  const put = (k: string, v: string | undefined | null, on: boolean) => {
    if (on && isSet(v)) p[k] = v.trim();
  };
  const datesOn = applies.has('dates');
  const hasDates = datesOn && (!!f.startDate || !!f.endDate);

  if (report === 'monthly_periods') {
    p.only_with_data = 'true';
    return { report, params: p };
  }

  put('start_date', f.startDate, datesOn);
  put('end_date', f.endDate, datesOn);
  put('month', f.month, applies.has('month') && !hasDates);
  put('brand', f.brand, applies.has('brand'));
  if (report === 'collections_overview') {
    put('territory_id', f.zoneId, applies.has('zone'));
  } else {
    put('zone_id', f.zoneId, applies.has('zone'));
  }
  put('area_id', f.areaId, applies.has('area'));
  put('employee_id', f.employeeId, applies.has('employee'));
  put('ageing_bucket', f.ageingBucket, applies.has('ageing'));
  put('collection_status', f.collectionStatus, applies.has('collectionStatus'));
  put('status', f.visitStatus, applies.has('visitStatus'));
  put('location_status', f.locationStatus, applies.has('locationStatus'));
  const q = f.search.trim();
  if (applies.has('search') && q) p[report === 'collections_overview' ? 'search' : 'query'] = q;
  return { report, params: p };
}

export interface FilterLookups {
  zones: Territory[];
  areas: Area[];
  employees: Employee[];
}

export interface AppliedFilterItem {
  label: string;
  value: string;
}

const COLLECTION_STATUS_LABEL: Record<string, string> = {
  NORMAL: 'Current / Not Due',
  WARNING: 'Warning (21-25 days)',
  OVERDUE: 'Overdue (26+ days)',
  PAID: 'Paid',
};

/** The "Applied filters" chips, derived from the exact params that were sent. */
export function describeAppliedFilters(req: ReportRequest, lookups: FilterLookups): AppliedFilterItem[] {
  const p = req.params;
  const out: AppliedFilterItem[] = [];
  if (p.start_date || p.end_date) {
    const a = p.start_date ? formatCalendarDate(p.start_date) : '';
    const b = p.end_date ? formatCalendarDate(p.end_date) : '';
    out.push({
      label: 'Date range (IST)',
      value: a && b ? `${a} to ${b}` : a ? `from ${a}` : `until ${b}`,
    });
  }
  if (p.month) out.push({ label: 'Month', value: formatMonthLabel(p.month) });
  if (p.brand) out.push({ label: 'Brand', value: p.brand });
  const zone = p.zone_id ?? p.territory_id;
  if (zone) out.push({ label: 'Zone', value: lookups.zones.find((z) => z.id === zone)?.name ?? zone });
  if (p.area_id) out.push({ label: 'Area', value: lookups.areas.find((a) => a.id === p.area_id)?.name ?? p.area_id });
  if (p.employee_id) {
    const e = lookups.employees.find((x) => x.id === p.employee_id);
    out.push({ label: 'Employee', value: e ? `${e.full_name} (${e.employee_code})` : p.employee_id });
  }
  if (p.ageing_bucket) out.push({ label: 'Ageing bucket', value: p.ageing_bucket });
  if (p.collection_status) {
    out.push({ label: 'Status', value: COLLECTION_STATUS_LABEL[p.collection_status] ?? p.collection_status });
  }
  if (p.status) out.push({ label: 'Status', value: p.status });
  if (p.location_status) out.push({ label: 'Location status', value: p.location_status });
  const q = p.query ?? p.search;
  if (q) out.push({ label: 'Search', value: `"${q}"` });
  return out;
}

/** Plain-language rules for what the filters mean on a tab (shown under the filter bar). */
export function tabSemanticsNotes(tab: ReportTabId, f: ReportFilterState, visitSubView: VisitSubView = 'register'): string[] {
  const notes: string[] = [];
  const hasDates = !!f.startDate || !!f.endDate;
  const snapshotTab = tab === 'financial_bi' || tab === 'outstanding' || tab === 'outlets';
  if (snapshotTab) {
    notes.push(
      'Sales and collection are summed over the snapshots in the period. Market outstanding and ageing buckets show the ' +
        'latest snapshot in the period (as of its date) and are never summed across dates.',
    );
    if (hasDates && f.month !== 'ALL') {
      notes.push('Month ignored: the date range takes priority over the month.');
    }
  } else if (tab === 'collections_workbench') {
    notes.push(
      "Outstanding, overdue and ageing are always as of today. 'Invoiced in period' and 'Collected in period (posted to " +
        "Tally)' follow the date range.",
    );
  } else if (tab === 'employees' || tab === 'visits') {
    notes.push(
      visitSubView === 'geo' && tab === 'visits'
        ? 'Dates are Asia/Kolkata (IST) days of the verification attempt.'
        : 'Dates are Asia/Kolkata (IST) days of the scheduled visit time.',
    );
  } else if (tab === 'monthly') {
    notes.push('Filters do not apply to Monthly Snapshots - every accounting period with data is listed.');
  }
  return notes;
}

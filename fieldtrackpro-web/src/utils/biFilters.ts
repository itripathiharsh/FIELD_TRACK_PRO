/**
 * Shared Dashboard + Reports BI filter vocabulary: the option lists for the multi-select filters
 * (Period / Month, Brand, FOS), the ageing buckets and their plain-language meaning, and the URL
 * query-parameter mapping. Both pages use these, so a filter means the same thing everywhere.
 */
import type { DashboardHistoryPeriod, Employee, MonthlyReportingPeriod } from '../types';
import type { MultiSelectOption } from '../components/filters/MultiSelectFilter';
import { splitMulti } from './multiValue';
import { formatMonthLabel } from './ist';

export interface BrandFilterOption {
  name: string;
  records: number;
  unattributed: boolean;
}

export const UNATTRIBUTED_BRAND = 'Unattributed';

/** Shape check for /brands/filter-options (an older backend answers that path differently). */
export function isBrandOptionList(v: unknown): v is BrandFilterOption[] {
  return Array.isArray(v) && v.every((b) => b && typeof b.name === 'string' && typeof b.records === 'number');
}

/** The 7 ageing buckets, in order, with the exact day ranges the backend uses. */
export const AGEING_BUCKETS: { key: string; label: string; days: string; tone: 'ok' | 'warn' | 'bad' }[] = [
  { key: '<15', label: '0-15 days', days: '0 to 15 days', tone: 'ok' },
  { key: '15-30', label: '16-30 days', days: '16 to 30 days', tone: 'ok' },
  { key: '30-45', label: '31-45 days', days: '31 to 45 days', tone: 'ok' },
  { key: '45-60', label: '46-60 days', days: '46 to 60 days', tone: 'warn' },
  { key: '60-75', label: '61-75 days', days: '61 to 75 days', tone: 'warn' },
  { key: '75-90', label: '76-90 days', days: '76 to 90 days', tone: 'bad' },
  { key: '>90', label: 'Over 90 days', days: 'more than 90 days', tone: 'bad' },
];

export const ageingLabel = (key: string): string => AGEING_BUCKETS.find((b) => b.key === key)?.label ?? key;

export const AGEING_EXPLAINER =
  'Each unpaid bill is placed in one bucket by its age: the number of days from the Tally bill (invoice) date to ' +
  'today, in India time. Click a bucket to show only the money in that bucket on every card, chart and table; ' +
  'click it again (or Reset) to see everything.';

const isLivePeriod = (p: MonthlyReportingPeriod) =>
  Number(p.total_sales) > 0 || Number(p.total_collection) > 0 || (p.snapshot_count ?? 0) > 0 || (p.total_outlets ?? 0) > 0;

/** Period / Month options: months with data (current year), then each history financial year and its months. */
export function periodOptions(periods: MonthlyReportingPeriod[], history: DashboardHistoryPeriod[]): MultiSelectOption[] {
  const out: MultiSelectOption[] = [];
  for (const p of periods.filter(isLivePeriod)) {
    const v = `${p.period_year}-${String(p.period_month).padStart(2, '0')}`;
    const tag = p.status === 'FINALIZED' ? 'Closed' : p.status === 'PENDING_CLOSE' ? 'Pending close' : 'Open';
    out.push({ value: v, label: p.period_name || formatMonthLabel(v), group: 'This financial year', hint: tag });
  }
  for (const fy of history) {
    const group = `History (read-only) · ${fy.label}`;
    out.push({ value: fy.value, label: `${fy.label} - full year`, group });
    for (const m of fy.months) out.push({ value: m.value, label: m.label, group });
  }
  return out;
}

export function brandOptions(brands: BrandFilterOption[]): MultiSelectOption[] {
  return brands.map((b) => ({
    value: b.name,
    label: b.unattributed ? 'Unattributed (no brand in Tally)' : b.name,
    hint: b.records.toLocaleString('en-IN'),
  }));
}

/** FOS = field staff. Admin / accountant accounts are not offered (they hold no outlets). */
export function fosOptions(employees: Employee[]): MultiSelectOption[] {
  return employees
    .filter((e) => !e.user?.role || e.user.role === 'EMPLOYEE')
    .map((e) => ({ value: e.id, label: e.employee_code ? `${e.full_name} (${e.employee_code})` : e.full_name }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** URL <-> filter state (comma-joined multi values, 'ALL' = not set). */
export const BI_QUERY_KEYS = {
  month: 'period',
  brand: 'brand',
  zoneId: 'zone',
  areaId: 'area',
  employeeId: 'fos',
  ageingBucket: 'ageing',
} as const;

export type BiFilterKey = keyof typeof BI_QUERY_KEYS;
export type BiFilterValues = Record<BiFilterKey, string>;

export const EMPTY_BI_FILTERS: BiFilterValues = {
  month: 'ALL', brand: 'ALL', zoneId: 'ALL', areaId: 'ALL', employeeId: 'ALL', ageingBucket: 'ALL',
};

export function biFiltersFromSearch(sp: URLSearchParams): BiFilterValues {
  const out = { ...EMPTY_BI_FILTERS };
  (Object.keys(BI_QUERY_KEYS) as BiFilterKey[]).forEach((k) => {
    const raw = sp.getAll(BI_QUERY_KEYS[k]).join(',');
    const vals = splitMulti(raw);
    if (vals.length) out[k] = k === 'zoneId' || k === 'areaId' || k === 'ageingBucket' ? vals[0] : vals.join(',');
  });
  if (out.ageingBucket !== 'ALL' && !AGEING_BUCKETS.some((b) => b.key === out.ageingBucket)) out.ageingBucket = 'ALL';
  return out;
}

/** Write the filters into the URL params (other params such as ?tab= are kept). */
export function writeBiFiltersToSearch(sp: URLSearchParams, f: BiFilterValues): URLSearchParams {
  const next = new URLSearchParams(sp);
  (Object.keys(BI_QUERY_KEYS) as BiFilterKey[]).forEach((k) => {
    next.delete(BI_QUERY_KEYS[k]);
    if (f[k] && f[k] !== 'ALL') next.set(BI_QUERY_KEYS[k], f[k]);
  });
  return next;
}

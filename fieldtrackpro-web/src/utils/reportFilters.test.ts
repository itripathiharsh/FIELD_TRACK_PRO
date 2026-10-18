import { describe, expect, it } from 'vitest';
import {
  ReportFilterState,
  applicableFilters,
  buildReportRequest,
  describeAppliedFilters,
  emptyReportFilters,
  reportForTab,
  tabSemanticsNotes,
} from './reportFilters';

const base = (over: Partial<ReportFilterState> = {}): ReportFilterState => ({ ...emptyReportFilters, ...over });
const lookups = {
  zones: [{ id: 'z1', name: 'North', created_at: '' }],
  areas: [{ id: 'a1', name: 'Area 1', territory_id: 'z1', territory_name: 'North', created_at: '' }],
  employees: [{ id: 'e1', full_name: 'Asha', employee_code: 'RF01' }] as never[],
};

const ALL_SET = base({
  month: '2026-09', brand: 'USHA', zoneId: 'z1', areaId: 'a1', employeeId: 'e1', ageingBucket: '>90', search: ' one ',
  startDate: '2026-08-01', endDate: '2026-08-31', collectionStatus: 'OVERDUE', visitStatus: 'COMPLETED', locationStatus: 'MISSING',
});

describe('reportFilters - which filters apply where', () => {
  it('maps every tab to its report', () => {
    expect(reportForTab('financial_bi')).toBe('business_summary');
    expect(reportForTab('collections_workbench')).toBe('collections_overview');
    expect(reportForTab('visits')).toBe('visits');
    expect(reportForTab('visits', 'geo')).toBe('geo');
    expect(reportForTab('employees')).toBe('staff');
    expect(reportForTab('monthly')).toBe('monthly_periods');
  });

  it('each tab only lists filters that change its data', () => {
    expect(applicableFilters('financial_bi')).not.toContain('search');
    expect(applicableFilters('financial_bi')).not.toContain('ageing');
    expect(applicableFilters('outstanding')).toEqual(expect.arrayContaining(['ageing', 'search', 'month', 'dates']));
    expect(applicableFilters('employees')).not.toContain('brand');
    expect(applicableFilters('employees')).not.toContain('month');
    expect(applicableFilters('visits')).toContain('visitStatus');
    expect(applicableFilters('visits', 'geo')).not.toContain('visitStatus');
    expect(applicableFilters('collections_workbench')).not.toContain('brand');
    expect(applicableFilters('monthly')).toEqual([]);
  });
});

describe('reportFilters - exact params per tab', () => {
  it('Financial & BI sends month/brand/zone/area/employee only', () => {
    const r = buildReportRequest('financial_bi', base({ ...ALL_SET, startDate: '', endDate: '' }));
    expect(r).toEqual({
      report: 'business_summary',
      params: { month: '2026-09', brand: 'USHA', zone_id: 'z1', area_id: 'a1', employee_id: 'e1' },
    });
  });

  it('a date range wins: the month is not sent', () => {
    const p = buildReportRequest('financial_bi', ALL_SET).params;
    expect(p.start_date).toBe('2026-08-01');
    expect(p.end_date).toBe('2026-08-31');
    expect(p).not.toHaveProperty('month');
  });

  it('one-sided ranges are sent as-is', () => {
    expect(buildReportRequest('outlets', base({ startDate: '2026-08-01' })).params).toEqual({ start_date: '2026-08-01' });
    expect(buildReportRequest('outlets', base({ endDate: '2026-08-31' })).params).toEqual({ end_date: '2026-08-31' });
  });

  it('Outstanding adds ageing + trimmed search as `query`', () => {
    const p = buildReportRequest('outstanding', ALL_SET).params;
    expect(p).toMatchObject({ ageing_bucket: '>90', query: 'one', brand: 'USHA', zone_id: 'z1', area_id: 'a1', employee_id: 'e1' });
    expect(p).not.toHaveProperty('status');
    expect(p).not.toHaveProperty('location_status');
  });

  it('Outlets sends location_status; Field Staff sends no brand/month/ageing', () => {
    expect(buildReportRequest('outlets', ALL_SET).params.location_status).toBe('MISSING');
    const staff = buildReportRequest('employees', ALL_SET).params;
    expect(Object.keys(staff).sort()).toEqual(['area_id', 'employee_id', 'end_date', 'query', 'start_date', 'zone_id']);
  });

  it('Visits sends status; the geo audit does not', () => {
    expect(buildReportRequest('visits', ALL_SET).params.status).toBe('COMPLETED');
    expect(buildReportRequest('visits', ALL_SET, 'geo').params).not.toHaveProperty('status');
    expect(buildReportRequest('visits', ALL_SET, 'geo').report).toBe('geo');
  });

  it('Collections workbench uses territory_id / search / collection_status and ignores brand, month, ageing', () => {
    const r = buildReportRequest('collections_workbench', ALL_SET);
    expect(r.report).toBe('collections_overview');
    expect(r.params).toEqual({
      start_date: '2026-08-01', end_date: '2026-08-31', territory_id: 'z1', area_id: 'a1', employee_id: 'e1',
      collection_status: 'OVERDUE', search: 'one',
    });
  });

  it('unset values (ALL / empty) are never sent, and Monthly sends only its own flag', () => {
    expect(buildReportRequest('outstanding', emptyReportFilters).params).toEqual({});
    expect(buildReportRequest('monthly', ALL_SET)).toEqual({ report: 'monthly_periods', params: { only_with_data: 'true' } });
  });
});

describe('reportFilters - applied filters strip + notes derive from the params', () => {
  it('describes exactly the params that were sent', () => {
    const req = buildReportRequest('outstanding', base({ brand: 'USHA', zoneId: 'z1', employeeId: 'e1', startDate: '2026-09-01', endDate: '2026-09-30', search: 'x' }));
    const items = describeAppliedFilters(req, lookups);
    expect(items).toEqual([
      { label: 'Date range (IST)', value: '01/09/2026 to 30/09/2026' },
      { label: 'Brand', value: 'USHA' },
      { label: 'Zone', value: 'North' },
      { label: 'Employee', value: 'Asha (RF01)' },
      { label: 'Search', value: '"x"' },
    ]);
  });

  it('does not list a filter that does not apply on the tab (e.g. brand on Field Staff)', () => {
    const items = describeAppliedFilters(buildReportRequest('employees', base({ brand: 'USHA', month: '2026-09' })), lookups);
    expect(items).toEqual([]);
  });

  it('formats months and one-sided ranges', () => {
    expect(describeAppliedFilters(buildReportRequest('outlets', base({ month: '2026-09' })), lookups)).toEqual([{ label: 'Month', value: 'September 2026' }]);
    expect(describeAppliedFilters(buildReportRequest('outlets', base({ startDate: '2026-09-01' })), lookups)[0].value).toBe('from 01/09/2026');
  });

  it('documents the period semantics per tab', () => {
    expect(tabSemanticsNotes('outstanding', base()).join(' ')).toMatch(/latest snapshot/i);
    expect(tabSemanticsNotes('outstanding', base({ month: '2026-09', startDate: '2026-09-01' })).join(' ')).toMatch(/month ignored/i);
    expect(tabSemanticsNotes('collections_workbench', base()).join(' ')).toMatch(/as of today/i);
    expect(tabSemanticsNotes('visits', base()).join(' ')).toMatch(/IST/);
    expect(tabSemanticsNotes('monthly', base()).join(' ')).toMatch(/do not apply/i);
  });
});

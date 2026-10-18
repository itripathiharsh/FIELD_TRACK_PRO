import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Wallet, Landmark, AlertTriangle, Building2, Filter, X } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { StatusBadge } from '../components/ui/StatusBadge';
import { AwaitingTallyAmount } from '../components/ui/AwaitingTallyAmount';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { PositionBreakdown, AgeingTable, ReconcileWarning } from '../components/collections/PositionBreakdown';
import { hasPosition } from '../components/collections/positionFormat';
import { AppliedFiltersStrip } from '../components/reports/AppliedFiltersStrip';
import { ExportButtons } from '../components/reports/ExportButtons';
import { useReportExport } from '../components/reports/useReportExport';
import { apiClient } from '../api/client';
import { Area, CollectionsOverviewTotals, Employee, OutletCollectionRow, Territory } from '../types';
import { formatCalendarDate } from '../utils/ist';
import {
  ReportFilterState,
  ReportRequest,
  buildReportRequest,
  describeAppliedFilters,
  emptyReportFilters,
  tabSemanticsNotes,
} from '../utils/reportFilters';
import { formatMoney as formatCurrency } from '../utils/money';

const PAGE_SIZE = 10;

const formatDate = (value: string): string =>
  new Date(value).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });

/** `Payment ₹50,000 · 12 Aug · Sandeep` or `Visit · 12 Aug · Sandeep` - whichever happened more recently. */
const formatLastActivity = (row: OutletCollectionRow): string => {
  const paymentTime = row.most_recent_payment_date ? new Date(row.most_recent_payment_date).getTime() : -Infinity;
  const visitTime = row.most_recent_visit_date ? new Date(row.most_recent_visit_date).getTime() : -Infinity;
  if (paymentTime === -Infinity && visitTime === -Infinity) return 'No activity yet';
  if (paymentTime >= visitTime) {
    const who = row.most_recent_payment_employee_name ? ` · ${row.most_recent_payment_employee_name}` : '';
    return `Payment ${formatCurrency(row.most_recent_payment_amount || '0')} · ${formatDate(row.most_recent_payment_date!)}${who}`;
  }
  const who = row.most_recent_visit_employee_name ? ` · ${row.most_recent_visit_employee_name}` : '';
  return `Visit · ${formatDate(row.most_recent_visit_date!)}${who}`;
};

interface Filters {
  search: string;
  territoryId: string;
  areaId: string;
  employeeId: string;
  collectionStatus: string;
  startDate: string;
  endDate: string;
}

const emptyFilters: Filters = { search: '', territoryId: '', areaId: '', employeeId: '', collectionStatus: '', startDate: '', endDate: '' };

/** Adapt this page's local filter shape to the shared ReportFilterState (single param builder). */
const toState = (f: Filters): ReportFilterState => ({
  ...emptyReportFilters,
  search: f.search,
  zoneId: f.territoryId || 'ALL',
  areaId: f.areaId || 'ALL',
  employeeId: f.employeeId || 'ALL',
  collectionStatus: f.collectionStatus,
  startDate: f.startDate,
  endDate: f.endDate,
});

export interface CollectionsOverviewPageProps {
  hideHeader?: boolean;
  /**
   * When embedded in the Reports page the global filter bar is the single source of truth:
   * it passes the exact request (params) and this page renders no filter card of its own.
   */
  externalRequest?: ReportRequest;
}

/**
 * Collections Overview - the outlet-list financial view (Meeting 2's
 * "Excel screenshot" replacement). Every number here comes straight from
 * GET /api/v1/collections/overview, which itself reuses aging_service and
 * account_service's exact calculations - nothing is computed client-side.
 */
export const CollectionsOverviewPage: React.FC<CollectionsOverviewPageProps> = ({ hideHeader = false, externalRequest }) => {
  const navigate = useNavigate();
  const [rows, setRows] = useState<OutletCollectionRow[]>([]);
  const [totals, setTotals] = useState<CollectionsOverviewTotals | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);

  // Draft filters are bound to the inputs and change on every keystroke/pick;
  // `applied` is what "Apply Filters" (or "Clear") last committed, and is the
  // only thing the fetch below depends on - mirrors ReportsPage's P1-13
  // draft-vs-applied pattern so typing never itself triggers a refetch.
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [applied, setApplied] = useState<Filters>(emptyFilters);
  const [dateError, setDateError] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [period, setPeriod] = useState<{ start: string | null; end: string | null }>({ start: null, end: null });
  const embedded = externalRequest !== undefined;
  // The exact request behind the table on screen (and behind the export).
  const request: ReportRequest = externalRequest ?? buildReportRequest('collections_workbench', toState(applied));
  const requestKey = JSON.stringify(request.params);
  const { exporting, run: runExport } = useReportExport(setError);

  useEffect(() => {
    apiClient.getEmployees().then(setEmployees).catch(() => setEmployees([]));
    apiClient.getTerritories().then(setTerritories).catch(() => setTerritories([]));
    apiClient.getAreas().then(setAreas).catch(() => setAreas([]));
  }, []);

  // Area options narrow to the selected Zone, since an outlet's Area always
  // belongs to exactly one Zone - picking a Zone first is how "Zone -> Area
  // -> Outlet" cascades in this filter bar.
  const areaOptions = draft.territoryId ? areas.filter((a) => a.territory_id === draft.territoryId) : areas;

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await apiClient.getCollectionsOverview({
        ...(JSON.parse(requestKey) as Record<string, string>),
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setRows(resp.outlets);
      setTotals(resp.totals);
      setTotalCount(resp.total_count);
      setAsOf(resp.as_of_date ?? null);
      setPeriod({ start: resp.period_start ?? null, end: resp.period_end ?? null });
    } catch (err) {
      setRows([]);
      setTotals(null);
      setError(err instanceof Error ? err.message : 'Unable to load the collections overview');
    } finally {
      setIsLoading(false);
    }
  }, [requestKey, page]);

  useEffect(() => {
    load();
  }, [load]);

  // A changed filter set (applied here, or pushed by the Reports page) restarts at page 1.
  useEffect(() => {
    setPage(1);
  }, [requestKey]);

  const applyFilters = () => {
    if (draft.startDate && draft.endDate && draft.endDate < draft.startDate) {
      setDateError('End date must be after start date');
      return;
    }
    setDateError(null);
    setApplied(draft);
    setPage(1);
  };

  const clearFilters = () => {
    setDraft(emptyFilters);
    setApplied(emptyFilters);
    setDateError(null);
    setPage(1);
  };

  const hasPeriod = totals?.invoiced_in_period != null;

  const filtersDirty = JSON.stringify(draft) !== JSON.stringify(applied);

  const showPos = rows.length > 0 ? hasPosition(rows[0]) : hasPosition(totals);
  const moneyCell = (v: string | undefined, testId?: string) => (
    <span data-testid={testId} className="text-sm text-on-surface whitespace-nowrap">{formatCurrency(v ?? 0)}</span>
  );

  const billedPaidColumns: Column<OutletCollectionRow>[] = showPos
    ? [
        { header: 'Opening (Tally)', accessor: (row) => moneyCell(row.opening_balance, 'row-opening') },
        { header: '+ Invoiced', accessor: (row) => moneyCell(row.total_invoiced, 'row-invoiced') },
        { header: '− Paid in Tally', accessor: (row) => moneyCell(row.paid_in_tally, 'row-paid') },
        {
          header: 'Awaiting Tally',
          accessor: (row) => (Number(row.verified_awaiting_tally_amount) > 0
            ? <AwaitingTallyAmount amount={row.verified_awaiting_tally_amount} />
            : <span className="text-xs text-on-surface-variant">—</span>),
        },
      ]
    : [
        {
          header: 'Billed / Paid',
          accessor: (row) => (
            <div className="font-caption text-xs space-y-0.5">
              <p className="text-on-surface">Billed: {formatCurrency(row.total_invoiced)}</p>
              <p className="text-on-surface-variant">Paid (in Tally): {formatCurrency(row.total_paid)}</p>
              <AwaitingTallyAmount amount={row.verified_awaiting_tally_amount} />
            </div>
          ),
        },
      ];

  const columns: Column<OutletCollectionRow>[] = [
    {
      header: 'Outlet',
      accessor: (row) => (
        <div className="">
          <p className="font-headline-sm text-sm text-primary font-bold" title={row.customer_name}>{row.customer_name}</p>
          <p className="font-caption text-xs text-on-surface-variant font-mono">{row.outlet_code || '—'}</p>
        </div>
      ),
    },
    {
      header: 'Zone / Area',
      accessor: (row) => (
        <div className="font-caption text-xs space-y-0.5">
          <p className="text-on-surface" title={row.territory_name || undefined}>{row.territory_name || '—'}</p>
          <p className="text-on-surface-variant" title={row.area_name || undefined}>{row.area_name || '—'}</p>
        </div>
      ),
    },
    {
      header: 'Assigned Employee',
      accessor: (row) => (
        <span
          className="block text-sm text-on-surface"
          title={row.assigned_employees.map((e) => e.name).join(', ') || undefined}
        >
          {row.assigned_employees.length > 0 ? row.assigned_employees.map((e) => e.name).join(', ') : '—'}
        </span>
      ),
    },
    ...billedPaidColumns,
    {
      header: 'Outstanding',
      accessor: (row) => (
        <p className={`font-headline-sm text-sm font-bold ${Number(row.total_outstanding) > 0 ? 'text-primary' : 'text-on-surface-variant'}`}>
          {formatCurrency(row.total_outstanding)}
        </p>
      ),
    },
    ...(showPos
      ? [
          {
            header: 'Overdue',
            accessor: (row: OutletCollectionRow) => (
              <div className="space-y-1">
                <span className={`text-sm font-semibold whitespace-nowrap ${Number(row.overdue_amount) > 0 ? 'text-rose-600' : 'text-on-surface-variant'}`}>
                  {formatCurrency(row.overdue_amount)}
                </span>
                <ReconcileWarning reconciles={row.reconciles} className="block w-fit" />
              </div>
            ),
          },
        ]
      : []),
    {
      header: 'Ageing / Status',
      accessor: (row) => (
        <div className="space-y-1">
          <StatusBadge status={row.collection_status} size="sm" />
          {row.relevant_mis_bucket && Number(row.relevant_bucket_amount) > 0 && (
            <p className="font-caption text-[11px] text-on-surface-variant">
              {formatCurrency(row.relevant_bucket_amount)} in {row.relevant_mis_bucket}d
            </p>
          )}
        </div>
      ),
    },
    ...(hasPeriod
      ? [
          {
            header: 'Invoiced in period',
            accessor: (row: OutletCollectionRow) => moneyCell(row.invoiced_in_period ?? '0', 'row-invoiced-period'),
          },
          {
            header: 'Collected in period (posted to Tally)',
            accessor: (row: OutletCollectionRow) => moneyCell(row.collected_in_period ?? '0', 'row-collected-period'),
          },
        ]
      : []),
    {
      header: 'Last Activity',
      accessor: (row) => <span className="font-caption text-xs text-on-surface-variant">{formatLastActivity(row)}</span>,
    },
  ];

  return (
    <div className="space-y-space-6">
      {!hideHeader && (
        <PageHeader
          title="Collections Overview"
          subtitle="Who owes money, how much, how old it is, who handles it, and when they were last paid or visited."
        />
      )}

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      {!embedded && (
        <AppliedFiltersStrip
          items={describeAppliedFilters(request, { zones: territories, areas, employees })}
          notes={tabSemanticsNotes('collections_workbench', toState(applied))}
        />
      )}
      <p data-testid="collections-asof" className="text-[11px] text-on-surface-variant">
        Outstanding, overdue and ageing are as of {asOf ? formatCalendarDate(asOf) : 'today'} (not the date range).
        {hasPeriod && (period.start || period.end)
          ? ` Period columns cover ${period.start ? formatCalendarDate(period.start) : 'the start'} to ${period.end ? formatCalendarDate(period.end) : 'today'} (IST).`
          : ''}
      </p>

      {/* Top summary - reflects the full filtered set, not just the current page */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-space-4">
        <MetricCard title="Total Outlets" value={totals?.total_outlets ?? '—'} icon={Building2} color="primary" />
        <MetricCard title="Total Billed" value={totals ? formatCurrency(totals.total_invoiced) : '—'} icon={Landmark} color="blue" />
        <MetricCard
          title="Total Paid (in Tally)"
          value={totals ? formatCurrency(showPos ? (totals.paid_in_tally ?? totals.total_paid) : totals.total_paid) : '—'}
          subtitle={totals && Number(totals.verified_awaiting_tally_amount) > 0 ? `Verified, awaiting Tally: ${formatCurrency(totals.verified_awaiting_tally_amount ?? 0)}` : undefined}
          icon={Wallet}
          color="emerald"
        />
        <MetricCard title="Total Outstanding" value={totals ? formatCurrency(totals.total_outstanding) : '—'} icon={AlertTriangle} color={totals && Number(totals.total_outstanding) > 0 ? 'rose' : 'slate'} />
        {hasPeriod && totals && (
          <>
            <MetricCard title="Invoiced in period" value={formatCurrency(totals.invoiced_in_period ?? 0)} icon={Landmark} color="blue" />
            <MetricCard title="Collected in period (posted to Tally)" value={formatCurrency(totals.collected_in_period ?? 0)} icon={Wallet} color="emerald" />
          </>
        )}
      </div>

      {totals && hasPosition(totals) && (
        <Card variant="flat">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-space-4">
            <div className="space-y-2">
              <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold">
                Totals for all outlets matching the filters
              </p>
              <PositionBreakdown position={totals} />
            </div>
            <AgeingTable ageing={totals.ageing} totalOutstanding={totals.total_outstanding} />
          </div>
        </Card>
      )}

      {!totals?.ageing && (
      <Card variant="flat">
        <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-3">
          Ageing Breakdown
        </p>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-space-3">
          {([
            ['Current', totals?.current_amount],
            ['0-15 Days', totals?.bucket_0_15],
            ['16-30 Days', totals?.bucket_16_30],
            ['31-60 Days', totals?.bucket_31_60],
            ['61-90 Days', totals?.bucket_61_90],
            ['90+ Days', totals?.bucket_90_plus],
          ] as [string, string | undefined][]).map(([label, amount]) => (
            <div key={label} className="p-space-3 bg-surface rounded-lg border border-outline-variant">
              <p className="font-caption text-[11px] uppercase tracking-wider text-on-surface-variant mb-1">{label}</p>
              <p className={`font-headline-sm text-sm font-bold ${label === '61-90 Days' || label === '90+ Days' ? 'text-error' : 'text-primary'}`}>
                {amount !== undefined ? formatCurrency(amount) : '—'}
              </p>
            </div>
          ))}
        </div>
      </Card>
      )}

      {!embedded && (
      <Card variant="flat">
        <div className="flex items-center gap-space-2 mb-space-4">
          <Filter className="w-4 h-4 text-on-surface-variant" />
          <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold">Filters</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-space-3">
          <div className="flex flex-col gap-space-1.5">
            <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
              Outlet Name / Code
            </label>
            <input
              type="text"
              value={draft.search}
              onChange={(e) => setDraft((p) => ({ ...p, search: e.target.value }))}
              placeholder="Search outlets..."
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
            />
          </div>
          <Select
            label="Zone"
            value={draft.territoryId}
            onChange={(e) => setDraft((p) => ({ ...p, territoryId: e.target.value, areaId: '' }))}
          >
            <option value="">All Zones</option>
            {territories.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </Select>
          <Select
            label="Area"
            value={draft.areaId}
            onChange={(e) => setDraft((p) => ({ ...p, areaId: e.target.value }))}
          >
            <option value="">All Areas</option>
            {areaOptions.map((a) => (
              <option key={a.id} value={a.id}>{a.name}{!draft.territoryId ? ` (${a.territory_name})` : ''}</option>
            ))}
          </Select>
          <Select
            label="Employee"
            value={draft.employeeId}
            onChange={(e) => setDraft((p) => ({ ...p, employeeId: e.target.value }))}
          >
            <option value="">All Employees</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>{e.full_name}</option>
            ))}
          </Select>
          <Select
            label="Ageing / Status"
            value={draft.collectionStatus}
            onChange={(e) => setDraft((p) => ({ ...p, collectionStatus: e.target.value }))}
          >
            <option value="">All Statuses</option>
            <option value="NORMAL">Current / Not Due</option>
            <option value="WARNING">Warning (21-25 days)</option>
            <option value="OVERDUE">Overdue (26+ days)</option>
            <option value="PAID">Paid</option>
          </Select>
        </div>
        <div className="flex flex-wrap items-center gap-space-2 mt-space-3">
          <span className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold">Date range (IST):</span>
          <input
            type="date"
            aria-label="Start date"
            value={draft.startDate}
            onChange={(e) => setDraft((p) => ({ ...p, startDate: e.target.value }))}
            className="h-8 bg-surface border border-outline-variant rounded-md px-2 py-1 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container"
          />
          <span className="text-on-surface-variant text-xs">to</span>
          <input
            type="date"
            aria-label="End date"
            value={draft.endDate}
            onChange={(e) => setDraft((p) => ({ ...p, endDate: e.target.value }))}
            className="h-8 bg-surface border border-outline-variant rounded-md px-2 py-1 text-xs text-on-surface font-body-md focus:outline-none focus:border-primary-container"
          />
          <span className="text-[11px] text-on-surface-variant">Adds Invoiced / Collected in period columns.</span>
        </div>
        {dateError && <p className="text-xs text-error font-medium pt-1">{dateError}</p>}
        <div className="flex items-center gap-space-3 mt-space-4">
          <Button variant="secondary" size="sm" onClick={applyFilters} disabled={isLoading}>
            Apply Filters
          </Button>
          <Button variant="ghost" size="sm" icon={X} onClick={clearFilters} disabled={isLoading}>
            Clear
          </Button>
          {filtersDirty && (
            <p className="text-xs text-on-surface-variant">Filter changed - click "Apply Filters" to update the results below.</p>
          )}
        </div>
      </Card>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold">
          {totalCount} outlet{totalCount === 1 ? '' : 's'} match
        </span>
        <ExportButtons
          onExport={(format) => runExport(request, format)}
          exporting={exporting}
          loading={isLoading}
          empty={totalCount === 0}
          emptyReason="No outlets match the current filters - nothing to export"
        />
      </div>

      <DataTable
        columns={columns}
        data={rows}
        rowKey={(row) => row.customer_id}
        isLoading={isLoading}
        emptyMessage="No outlets match the current filters"
        onRowClick={(row) => navigate(`/customers/${row.customer_id}`)}
        serverSide
        totalCount={totalCount}
        pageSize={PAGE_SIZE}
        page={page}
        onPageChange={setPage}
      />
    </div>
  );
};

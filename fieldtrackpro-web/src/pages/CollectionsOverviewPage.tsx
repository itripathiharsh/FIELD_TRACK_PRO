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
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { apiClient } from '../api/client';
import { Area, CollectionsOverviewTotals, Employee, OutletCollectionRow, Territory } from '../types';

const PAGE_SIZE = 10;

const formatCurrency = (value: string | number): string => {
  const n = Number(value);
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
};

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
}

const emptyFilters: Filters = { search: '', territoryId: '', areaId: '', employeeId: '', collectionStatus: '' };

export interface CollectionsOverviewPageProps {
  hideHeader?: boolean;
}

/**
 * Collections Overview - the outlet-list financial view (Meeting 2's
 * "Excel screenshot" replacement). Every number here comes straight from
 * GET /api/v1/collections/overview, which itself reuses aging_service and
 * account_service's exact calculations - nothing is computed client-side.
 */
export const CollectionsOverviewPage: React.FC<CollectionsOverviewPageProps> = ({ hideHeader = false }) => {
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
        search: applied.search || undefined,
        territory_id: applied.territoryId || undefined,
        area_id: applied.areaId || undefined,
        employee_id: applied.employeeId || undefined,
        collection_status: applied.collectionStatus || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setRows(resp.outlets);
      setTotals(resp.totals);
      setTotalCount(resp.total_count);
    } catch (err) {
      setRows([]);
      setTotals(null);
      setError(err instanceof Error ? err.message : 'Unable to load the collections overview');
    } finally {
      setIsLoading(false);
    }
  }, [applied, page]);

  useEffect(() => {
    load();
  }, [load]);

  const applyFilters = () => {
    setApplied(draft);
    setPage(1);
  };

  const clearFilters = () => {
    setDraft(emptyFilters);
    setApplied(emptyFilters);
    setPage(1);
  };

  const filtersDirty = JSON.stringify(draft) !== JSON.stringify(applied);

  const columns: Column<OutletCollectionRow>[] = [
    {
      header: 'Outlet',
      accessor: (row) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{row.customer_name}</p>
          <p className="font-caption text-xs text-on-surface-variant font-mono">{row.outlet_code || '—'}</p>
        </div>
      ),
    },
    {
      header: 'Zone / Area',
      accessor: (row) => (
        <div className="font-caption text-xs space-y-0.5">
          <p className="text-on-surface">{row.territory_name || '—'}</p>
          <p className="text-on-surface-variant">{row.area_name || '—'}</p>
        </div>
      ),
    },
    {
      header: 'Assigned Employee',
      accessor: (row) => (
        <span className="text-sm text-on-surface">
          {row.assigned_employees.length > 0 ? row.assigned_employees.map((e) => e.name).join(', ') : '—'}
        </span>
      ),
    },
    {
      header: 'Billed / Paid',
      accessor: (row) => (
        <div className="font-caption text-xs space-y-0.5">
          <p className="text-on-surface">Billed: {formatCurrency(row.total_invoiced)}</p>
          <p className="text-on-surface-variant">Paid: {formatCurrency(row.total_paid)}</p>
        </div>
      ),
    },
    {
      header: 'Outstanding',
      accessor: (row) => (
        <p className={`font-headline-sm text-sm font-bold ${Number(row.total_outstanding) > 0 ? 'text-primary' : 'text-on-surface-variant'}`}>
          {formatCurrency(row.total_outstanding)}
        </p>
      ),
    },
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

      {/* Top summary - reflects the full filtered set, not just the current page */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-space-4">
        <MetricCard title="Total Outlets" value={totals?.total_outlets ?? '—'} icon={Building2} color="primary" />
        <MetricCard title="Total Billed" value={totals ? formatCurrency(totals.total_invoiced) : '—'} icon={Landmark} color="blue" />
        <MetricCard title="Total Paid" value={totals ? formatCurrency(totals.total_paid) : '—'} icon={Wallet} color="emerald" />
        <MetricCard title="Total Outstanding" value={totals ? formatCurrency(totals.total_outstanding) : '—'} icon={AlertTriangle} color={totals && Number(totals.total_outstanding) > 0 ? 'rose' : 'slate'} />
      </div>

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

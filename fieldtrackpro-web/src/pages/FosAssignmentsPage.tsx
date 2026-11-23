import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, ListChecks } from 'lucide-react';
import { apiClient } from '../api/client';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { StatusBadge } from '../components/ui/StatusBadge';
import { DataTable, Column } from '../components/ui/DataTable';
import type {
  Employee, FosAuditEntry, FosGroup, FosReconciliation, FosStatus, FosSummary, OutletFos,
} from '../types';

/**
 * FOS assignments, synchronised from Tally.
 *
 * Tally is the source of truth: the accountant moves a customer ledger into a FOS's ledger group in Tally and the
 * next ledger sync updates FieldTrack. This page is therefore a READ-ONLY view of the assignments, except for the
 * one thing FieldTrack has to decide itself: which employee a Tally group stands for ("Tally groups" tab).
 */
type Tab = 'outlets' | 'groups' | 'reconciliation' | 'audit';
const TABS: { key: Tab; label: string }[] = [
  { key: 'outlets', label: 'Outlets' },
  { key: 'groups', label: 'Tally groups' },
  { key: 'reconciliation', label: 'Reconciliation' },
  { key: 'audit', label: 'Change log' },
];

const STATUS_LABEL: Record<string, string> = {
  ASSIGNED: 'Assigned',
  MULTIPLE: 'Several FOS',
  UNASSIGNED: 'No FOS in Tally',
  UNMAPPED_GROUP: 'Group not mapped',
  CONFLICT: 'Conflict',
  NO_TALLY: 'Not in Tally',
  NOT_SYNCED: 'Not synced yet',
};
const STATUS_TONE: Record<string, string> = {
  ASSIGNED: 'COMPLETED', MULTIPLE: 'COMPLETED', UNASSIGNED: 'PENDING', UNMAPPED_GROUP: 'PENDING',
  CONFLICT: 'REJECTED', NO_TALLY: 'PENDING', NOT_SYNCED: 'PENDING',
};
const PAGE_SIZE = 50;

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');
const when = (v: string | null | undefined) => (v ? new Date(v).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '-');

const FosStatusBadge: React.FC<{ status: FosStatus | 'NOT_SYNCED' | null }> = ({ status }) => {
  const key = status ?? 'NOT_SYNCED';
  return <StatusBadge status={STATUS_TONE[key] ?? 'PENDING'} label={STATUS_LABEL[key] ?? key} size="sm" />;
};

// ------------------------------------------------------------------------------------------------ Outlets
const OutletsTab: React.FC<{ employees: Employee[]; groups: string[] }> = ({ employees, groups }) => {
  const [assignment, setAssignment] = useState<'all' | 'assigned' | 'unassigned'>('all');
  const [status, setStatus] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [group, setGroup] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<OutletFos[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debounced, setDebounced] = useState('');

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const onSearch = (q: string) => {
    setSearch(q);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { setDebounced(q.trim()); setPage(1); }, 300);
  };

  useEffect(() => {
    let live = true;
    setLoading(true);
    apiClient
      .getFosOutlets({
        assignment, status: status || undefined, employee_id: employeeId || undefined, group: group || undefined,
        search: debounced || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE,
      })
      .then((r) => { if (live) { setRows(r.items); setTotal(r.total); setError(null); } })
      .catch((e) => { if (live) setError(errMsg(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [assignment, status, employeeId, group, debounced, page]);

  const reset = (fn: () => void) => { fn(); setPage(1); };

  const columns: Column<OutletFos>[] = [
    { header: 'Outlet', accessor: (r) => (<div><div className="font-medium">{r.name}</div>{r.outlet_code && <div className="text-xs text-on-surface-variant">{r.outlet_code}</div>}</div>) },
    { header: 'Tally group', accessor: (r) => r.tally_group ?? '-' },
    {
      header: 'Assigned FOS',
      accessor: (r) => (r.fos.length === 0 ? <span className="text-on-surface-variant">Unassigned</span>
        : r.fos.map((f) => (
          <div key={f.employee_id}>{f.name}{f.source !== 'TALLY' && <span className="ml-1 text-xs text-on-surface-variant" title="Created before the Tally sync; kept until reconciled">({f.source.toLowerCase()})</span>}</div>
        ))),
    },
    { header: 'Status', accessor: (r) => <FosStatusBadge status={r.fos_status} /> },
    { header: 'Last synced', accessor: (r) => when(r.fos_synced_at) },
  ];

  return (
    <div className="space-y-space-4">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-space-3">
        <Select label="Assignment" value={assignment} onChange={(e) => reset(() => setAssignment(e.target.value as 'all'))}>
          <option value="all">All outlets</option>
          <option value="assigned">Assigned outlets</option>
          <option value="unassigned">Unassigned outlets</option>
        </Select>
        <Select label="FOS" value={employeeId} onChange={(e) => reset(() => setEmployeeId(e.target.value))}>
          <option value="">Any FOS</option>
          {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
        </Select>
        <Select label="Status" value={status} onChange={(e) => reset(() => setStatus(e.target.value))}>
          <option value="">Any status</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select label="Tally group" value={group} onChange={(e) => reset(() => setGroup(e.target.value))}>
          <option value="">Any group</option>
          {groups.map((g) => <option key={g} value={g}>{g}</option>)}
        </Select>
      </div>
      <DataTable
        columns={columns}
        data={rows}
        serverSide
        totalCount={total}
        pageSize={PAGE_SIZE}
        page={page}
        onPageChange={setPage}
        onSearchChange={onSearch}
        searchPlaceholder="Search outlet name or code..."
        isLoading={loading}
        emptyMessage="No outlets match these filters."
        rowKey={(r) => r.id}
      />
      <span className="sr-only">{search}</span>
    </div>
  );
};

// ------------------------------------------------------------------------------------------------ Groups
const GroupRow: React.FC<{ g: FosGroup; employees: Employee[]; onSaved: () => void; onError: (m: string) => void }> = ({ g, employees, onSaved, onError }) => {
  const [pick, setPick] = useState(g.employee_id ?? g.suggested_employee_id ?? '');
  const [busy, setBusy] = useState(false);
  const run = async (body: { employee_id?: string | null; not_fos?: boolean }) => {
    setBusy(true);
    try { await apiClient.mapFosGroup(g.id, body); onSaved(); } catch (e) { onError(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <tr className="border-t border-surface-container-highest align-top">
      <td className="px-3 py-2"><div className="font-medium">{g.group_name}</div>
        {g.suggested_employee_name && g.status === 'UNMAPPED' && <div className="text-xs text-on-surface-variant">Suggested: {g.suggested_employee_name} ({g.suggestion_basis})</div>}</td>
      <td className="px-3 py-2 text-right">{g.outlets}</td>
      <td className="px-3 py-2 text-right">{g.assigned_outlets}</td>
      <td className="px-3 py-2">
        <StatusBadge status={g.status === 'MAPPED' ? 'COMPLETED' : 'PENDING'} size="sm"
          label={g.status === 'MAPPED' ? `FOS: ${g.employee_name ?? '?'}` : g.status === 'NOT_FOS' ? 'Not a FOS group' : 'Not mapped'} />
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-2 items-center">
          <select aria-label={`Employee for ${g.group_name}`} className="border border-outline-variant rounded px-2 py-1 text-sm bg-surface"
            value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Choose employee...</option>
            {employees.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
          </select>
          <Button size="sm" disabled={!pick || busy} onClick={() => run({ employee_id: pick })}>Map</Button>
          <Button size="sm" variant="secondary" disabled={busy || g.status === 'NOT_FOS'} onClick={() => run({ not_fos: true })}>Not a FOS group</Button>
          {g.status !== 'UNMAPPED' && <Button size="sm" variant="secondary" disabled={busy} onClick={() => run({})}>Unmap</Button>}
        </div>
      </td>
    </tr>
  );
};

const GroupsTab: React.FC<{ employees: Employee[]; onChanged: () => void }> = ({ employees, onChanged }) => {
  const [groups, setGroups] = useState<FosGroup[]>([]);
  const [filter, setFilter] = useState<'ALL' | 'UNMAPPED'>('UNMAPPED');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    setLoading(true);
    apiClient.getFosGroups().then((g) => { setGroups(g); setError(null); }).catch((e) => setError(errMsg(e))).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);
  const shown = filter === 'UNMAPPED' ? groups.filter((g) => g.status === 'UNMAPPED') : groups;
  return (
    <div className="space-y-space-4">
      {error && <ErrorBanner message={error} />}
      <p className="text-sm text-on-surface-variant">
        In Tally a FOS is a ledger group (for example &quot;Raunak Usha&quot;). Tell FieldTrack which employee each group stands for;
        outlets in a group follow it automatically. Groups that are not a salesperson (for example &quot;Sundry Debtors&quot;) are marked
        &quot;Not a FOS group&quot;. Nothing is ever mapped on a guess: a suggestion is only pre-selected.
      </p>
      <div className="max-w-xs">
        <Select label="Show" value={filter} onChange={(e) => setFilter(e.target.value as 'ALL')}>
          <option value="UNMAPPED">Groups needing a decision</option>
          <option value="ALL">All groups</option>
        </Select>
      </div>
      <div className="overflow-x-auto bg-surface rounded-xl border border-surface-container-highest">
        <table className="w-full text-sm">
          <thead className="bg-surface-container text-left text-xs uppercase tracking-wider">
            <tr><th className="px-3 py-2">Tally group</th><th className="px-3 py-2 text-right">Outlets</th><th className="px-3 py-2 text-right">With FOS</th><th className="px-3 py-2">Meaning</th><th className="px-3 py-2">Decision</th></tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={5} className="px-3 py-4 text-on-surface-variant">Loading...</td></tr>}
            {!loading && shown.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-on-surface-variant">Every Tally group has been decided.</td></tr>}
            {shown.map((g) => <GroupRow key={`${g.id}-${g.status}-${g.employee_id}`} g={g} employees={employees} onSaved={() => { load(); onChanged(); }} onError={setError} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------------------------------------ Reconciliation
const RECON_LABELS: Record<string, string> = {
  matching: 'Matching: FieldTrack and Tally agree',
  new_from_tally: 'New: Tally assigns a FOS, FieldTrack has none',
  conflicting: 'Conflicting: FieldTrack has a different FOS (kept until approved)',
  assigned_here_blank_in_tally: 'Assigned in FieldTrack, no FOS in Tally',
  missing_employee_mapping: 'Tally group not mapped to an employee',
  unassigned_in_both: 'Unassigned in both',
  changed: 'Will change',
  no_tally_ledger_with_assignment: 'Not in Tally, has an assignment (left alone)',
};

const ReconciliationTab: React.FC<{ summary: FosSummary | null; onChanged: () => void }> = ({ summary, onChanged }) => {
  const [rep, setRep] = useState<FosReconciliation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const check = async () => {
    setBusy(true); setNote(null);
    try { setRep(await apiClient.getFosReconciliation()); setError(null); } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  const apply = async () => {
    setBusy(true);
    try { const r = await apiClient.runFosSync(false); setNote(`Synchronised. ${JSON.stringify((r.summary as { counts?: unknown } | null)?.counts ?? {})}`); onChanged(); await check(); }
    catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-space-4">
      {error && <ErrorBanner message={error} />}
      {note && <div role="status" className="text-sm p-3 rounded bg-surface-container">{note}</div>}
      <div className="flex flex-wrap gap-2">
        <Button onClick={check} disabled={busy}><ListChecks size={16} className="mr-1" /> Check against Tally (no changes)</Button>
        <Button variant="secondary" onClick={apply} disabled={busy || !summary?.sync_enabled}
          title={summary?.sync_enabled ? 'Apply Tally assignments now' : 'Synchronisation is not switched on for this server'}>
          <RefreshCw size={16} className="mr-1" /> Synchronise now
        </Button>
      </div>
      {rep && (
        <>
          <p className="text-sm text-on-surface-variant">Checked {rep.outlets_evaluated} outlets at {when(rep.generated_at)}. Nothing was changed.</p>
          <table className="w-full text-sm bg-surface rounded-xl border border-surface-container-highest">
            <tbody>
              {Object.entries(RECON_LABELS).map(([k, label]) => (
                <tr key={k} className="border-t border-surface-container-highest first:border-t-0">
                  <td className="px-3 py-2">{label}</td><td className="px-3 py-2 text-right font-medium">{rep.counts[k] ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rep.unmatched_salesperson_groups.length > 0 && (
            <Card>
              <div className="p-space-4">
                <h3 className="font-semibold mb-1">Tally groups still waiting for a decision ({rep.unmatched_salesperson_groups.length})</h3>
                <p className="text-sm text-on-surface-variant mb-2">Map them on the &quot;Tally groups&quot; tab. Outlets in these groups keep whatever access they have now.</p>
                <ul className="text-sm columns-1 sm:columns-2 lg:columns-3">{rep.unmatched_salesperson_groups.map((g) => <li key={g}>{g}</li>)}</ul>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

// ------------------------------------------------------------------------------------------------ Audit
const AuditTab: React.FC = () => {
  const [rows, setRows] = useState<FosAuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    apiClient.getFosAudit({ limit: 200 }).then(setRows).catch((e) => setError(errMsg(e))).finally(() => setLoading(false));
  }, []);
  const columns: Column<FosAuditEntry>[] = [
    { header: 'When', accessor: (r) => when(r.created_at) },
    { header: 'Outlet / group', accessor: (r) => r.customer_name ?? r.tally_group ?? '-' },
    { header: 'Previous FOS', accessor: (r) => r.previous_fos ?? '-' },
    { header: 'New FOS', accessor: (r) => r.new_fos ?? '-' },
    { header: 'Change', accessor: (r) => r.action },
    { header: 'Source', accessor: (r) => r.source },
    { header: 'Tally group', accessor: (r) => r.tally_group ?? '-' },
    { header: 'Result', accessor: (r) => r.result },
  ];
  return (
    <div className="space-y-space-4">
      {error && <ErrorBanner message={error} />}
      <DataTable columns={columns} data={rows} isLoading={loading} emptyMessage="No FOS changes have been recorded yet." rowKey={(r) => r.id}
        searchPlaceholder="Search the change log..."
        searchFilter={(r, q) => `${r.customer_name ?? ''} ${r.tally_group ?? ''} ${r.previous_fos ?? ''} ${r.new_fos ?? ''}`.toLowerCase().includes(q.toLowerCase())} />
    </div>
  );
};

// ------------------------------------------------------------------------------------------------ Page
export const FosAssignmentsPage: React.FC = () => {
  const [tab, setTab] = useState<Tab>('outlets');
  const [summary, setSummary] = useState<FosSummary | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [groupNames, setGroupNames] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(() => {
    apiClient.getFosSummary().then(setSummary).catch((e) => setError(errMsg(e)));
    apiClient.getFosGroups().then((g) => setGroupNames(g.map((x) => x.group_name).sort((a, b) => a.localeCompare(b)))).catch(() => undefined);
  }, []);
  useEffect(() => {
    loadSummary();
    apiClient.getEmployees({ limit: 500, is_active: true }).then(setEmployees).catch((e) => setError(errMsg(e)));
  }, [loadSummary]);

  const unmapped = summary?.groups?.UNMAPPED ?? 0;
  const fieldStaff = useMemo(() => employees.filter((e) => e.user?.role !== 'ACCOUNTANT'), [employees]);

  return (
    <div>
      <PageHeader
        title="FOS Assignments"
        subtitle="Synchronised from Tally. The accountant assigns the FOS in Tally; FieldTrack shows what it received."
      />
      {error && <ErrorBanner message={error} />}
      {summary && !summary.sync_enabled && (
        <div role="note" className="mb-space-4 p-3 rounded-lg bg-surface-container text-sm">
          Automatic synchronisation is not switched on for this server yet. The assignments below are the ones that already existed; nothing will change from Tally until it is enabled.
        </div>
      )}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-space-3 mb-space-4">
          {[
            ['Outlets', summary.total_outlets], ['With a FOS', summary.outlets_with_fos], ['Without a FOS', summary.outlets_without_fos],
            ['Groups to map', unmapped], ['Last synced', when(summary.last_synced_at)],
          ].map(([label, value]) => (
            <Card key={String(label)}><div className="p-space-3"><div className="text-xs uppercase tracking-wider text-on-surface-variant">{label}</div><div className="text-xl font-semibold">{value}</div></div></Card>
          ))}
        </div>
      )}
      <div role="tablist" className="flex gap-2 mb-space-4 border-b border-surface-container-highest">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-sm font-medium border-b-2 ${tab === t.key ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant'}`}>
            {t.label}{t.key === 'groups' && unmapped > 0 ? ` (${unmapped})` : ''}
          </button>
        ))}
      </div>
      {tab === 'outlets' && <OutletsTab employees={fieldStaff} groups={groupNames} />}
      {tab === 'groups' && <GroupsTab employees={fieldStaff} onChanged={loadSummary} />}
      {tab === 'reconciliation' && <ReconciliationTab summary={summary} onChanged={loadSummary} />}
      {tab === 'audit' && <AuditTab />}
    </div>
  );
};

export default FosAssignmentsPage;

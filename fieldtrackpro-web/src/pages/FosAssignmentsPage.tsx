import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, ListChecks, Users, Info } from 'lucide-react';
import { apiClient } from '../api/client';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { StatusBadge } from '../components/ui/StatusBadge';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { formatIstDateTime } from '../utils/ist';
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
const TABS: { key: Tab; label: string; help: string }[] = [
  { key: 'outlets', label: 'Outlets', help: 'Every outlet and its FOS. Use "Change FOS" to reassign one outlet; Tally is updated by moving its ledger.' },
  {
    key: 'groups',
    label: 'Tally groups (FOS mapping)',
    help: 'Each Tally ledger group and the employee it stands for. This is the only place where FieldTrack decides something.',
  },
  {
    key: 'reconciliation',
    label: 'Check against Tally',
    help: 'Compares FieldTrack with Tally and lists what would change. Checking changes nothing.',
  },
  { key: 'audit', label: 'Change log', help: 'Every FOS change: who or what changed it, when, from which Tally group.' },
];

/** What each outlet status means, in plain words (shown as a legend on the Outlets tab). */
const STATUS_HELP: Record<string, string> = {
  ASSIGNED: "The outlet's Tally group is mapped to one employee, who is its FOS.",
  MULTIPLE: 'The shop has ledgers in several mapped groups (for example one per brand), so it has several FOS.',
  UNASSIGNED: 'The ledger sits in a Tally group that is not a salesperson (for example "Sundry Debtors").',
  UNMAPPED_GROUP: 'The Tally group has not been mapped to an employee yet. Map it on the "Tally groups" tab.',
  CONFLICT: 'FieldTrack and Tally disagree about this outlet. The FieldTrack FOS is kept until an admin decides.',
  ADMIN_PENDING: 'An admin changed the FOS here. Waiting for the accountant to move the ledger in Tally; the next sync confirms it.',
  NO_TALLY: 'This outlet has no Tally ledger, so Tally cannot give it a FOS. Its existing assignment is left alone.',
  NOT_SYNCED: 'Not checked against Tally yet.',
};

const STATUS_LABEL: Record<string, string> = {
  ASSIGNED: 'Assigned',
  MULTIPLE: 'Several FOS',
  UNASSIGNED: 'No FOS in Tally',
  UNMAPPED_GROUP: 'Group not mapped',
  CONFLICT: 'Conflict',
  ADMIN_PENDING: 'Changed here, awaiting Tally',
  NO_TALLY: 'Not in Tally',
  NOT_SYNCED: 'Not synced yet',
};
const STATUS_TONE: Record<string, string> = {
  ASSIGNED: 'COMPLETED', MULTIPLE: 'COMPLETED', UNASSIGNED: 'PENDING', UNMAPPED_GROUP: 'PENDING',
  CONFLICT: 'REJECTED', NO_TALLY: 'PENDING', NOT_SYNCED: 'PENDING', ADMIN_PENDING: 'PENDING',
};
const PAGE_SIZE = 50;

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');
const when = (v: string | null | undefined) => (v ? `${formatIstDateTime(v)} IST` : '-');

const FosStatusBadge: React.FC<{ status: FosStatus | 'NOT_SYNCED' | null }> = ({ status }) => {
  const key = status ?? 'NOT_SYNCED';
  return <StatusBadge status={STATUS_TONE[key] ?? 'PENDING'} label={STATUS_LABEL[key] ?? key} size="sm" />;
};

// ------------------------------------------------------------------------------------------------ Outlets
/** "Change FOS" for one outlet: current FOS, the new one, what happens in Tally, then an explicit confirmation. */
const ChangeFosDialog: React.FC<{ outlet: OutletFos; employees: Employee[]; onClose: () => void; onSaved: (msg: string) => void }> = ({
  outlet, employees, onClose, onSaved,
}) => {
  const [pick, setPick] = useState('');
  const [note, setNote] = useState('');
  const [step, setStep] = useState<'choose' | 'confirm'>('choose');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useMemo(() => `fos-${outlet.id}-${Date.now()}`, [outlet.id]);
  const current = outlet.fos.map((f) => f.name).join(', ') || 'No FOS';
  const target = employees.find((e) => e.id === pick)?.full_name ?? '';
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const mv = await apiClient.changeOutletFos(
        outlet.id,
        { employee_id: pick, expected_employee_ids: outlet.fos.map((f) => f.employee_id), note: note.trim() || undefined },
        key,
      );
      onSaved(
        mv.status === 'CONFIRMED'
          ? `${outlet.name}: FOS changed to ${target}.`
          : `${outlet.name}: FOS changed to ${target}. In Tally, move ledger "${mv.ledger_name ?? outlet.name}" ` +
            (mv.to_group ? `to "${mv.to_group}"` : "to the new FOS's group") + '; the next sync confirms it.',
      );
    } catch (e) {
      setError(errMsg(e));
      setStep('choose');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal isOpen onClose={() => !busy && onClose()} title={`Change FOS: ${outlet.name}`}>
      <div className="space-y-3 text-sm" data-testid="change-fos-dialog">
        {error && <ErrorBanner message={error} />}
        <div><span className="text-on-surface-variant">Current FOS: </span><strong>{current}</strong></div>
        {outlet.tally_group && <div><span className="text-on-surface-variant">Tally group now: </span>{outlet.tally_group}</div>}
        {step === 'choose' ? (
          <>
            <Select label="New FOS" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Choose an active employee...</option>
              {employees.filter((e) => !outlet.fos.some((f) => f.employee_id === e.id) || outlet.fos.length > 1)
                .map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}
            </Select>
            <label className="block text-xs font-semibold">Note (optional)
              <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300}
                className="mt-1 w-full border border-outline-variant rounded px-2 py-1 text-sm bg-surface" />
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button disabled={!pick} onClick={() => setStep('confirm')}>Continue</Button>
            </div>
          </>
        ) : (
          <>
            <p className="font-semibold">Change the FOS of {outlet.name} from {current} to {target}?</p>
            <ul className="list-disc pl-5 space-y-1 text-on-surface-variant">
              <li>{target} gets this outlet in the app now; {current === 'No FOS' ? 'nobody loses it' : `${current} no longer sees it`}.</li>
              <li>Tally still has the ledger under its old group. The accountant must move it to {target}&apos;s group in Tally;
                until then FieldTrack keeps your change and the Tally sync does not undo it.</li>
              <li>If Tally moves the ledger to a different FOS instead, the outlet is flagged as a conflict for you to decide; nothing is overwritten.</li>
              <li>Recorded in the Change log with you as the author. No invoice, receipt or amount changes.</li>
            </ul>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setStep('choose')} disabled={busy}>Back</Button>
              <Button onClick={save} isLoading={busy}>Confirm change</Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};

const ResolveDialog: React.FC<{ outlet: OutletFos; onClose: () => void; onSaved: (msg: string) => void }> = ({ outlet, onClose, onSaved }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mv = outlet.pending_move!;
  const go = async (keep: 'ADMIN' | 'TALLY') => {
    setBusy(true);
    try {
      await apiClient.resolveFosMove(mv.id, keep);
      onSaved(keep === 'ADMIN' ? `${outlet.name}: FieldTrack FOS kept; waiting for Tally again.` : `${outlet.name}: Tally's FOS applies.`);
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Modal isOpen onClose={() => !busy && onClose()} title={`Resolve FOS conflict: ${outlet.name}`}>
      <div className="space-y-3 text-sm">
        {error && <ErrorBanner message={error} />}
        <p>FieldTrack has <strong>{outlet.fos.map((f) => f.name).join(', ') || 'no FOS'}</strong>; in Tally the ledger was moved from
          &quot;{mv.from_group}&quot; to &quot;{outlet.tally_group}&quot; instead of {mv.to_group ? `"${mv.to_group}"` : 'the new FOS group'}.</p>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="secondary" onClick={() => go('TALLY')} disabled={busy}>Use Tally&apos;s FOS</Button>
          <Button onClick={() => go('ADMIN')} disabled={busy}>Keep FieldTrack&apos;s FOS</Button>
        </div>
      </div>
    </Modal>
  );
};

const OutletsTab: React.FC<{ employees: Employee[]; groups: string[] }> = ({ employees, groups }) => {
  const [editing, setEditing] = useState<OutletFos | null>(null);
  const [resolving, setResolving] = useState<OutletFos | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
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
  }, [assignment, status, employeeId, group, debounced, page, reload]);

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
    {
      header: 'Status',
      accessor: (r) => (
        <div className="space-y-1">
          <FosStatusBadge status={r.fos_status} />
          {r.pending_move?.status === 'PENDING_TALLY' && (
            <div className="text-xs text-on-surface-variant">Move in Tally to {r.pending_move.to_group ? `"${r.pending_move.to_group}"` : "the new FOS's group"}</div>
          )}
        </div>
      ),
    },
    { header: 'Last synced', accessor: (r) => when(r.fos_synced_at) },
    {
      header: 'Action',
      accessor: (r) => (
        <div className="flex flex-wrap gap-1">
          <Button size="sm" variant="secondary" onClick={() => setEditing(r)} aria-label={`Change FOS of ${r.name}`}>Change FOS</Button>
          {r.pending_move?.status === 'CONFLICT' && (
            <Button size="sm" onClick={() => setResolving(r)}>Resolve</Button>
          )}
        </div>
      ),
    },
  ];

  const saved = (msg: string) => {
    setEditing(null);
    setResolving(null);
    setDone(msg);
    setReload((n) => n + 1);
  };

  return (
    <div className="space-y-space-4">
      {error && <ErrorBanner message={error} />}
      {done && <div role="status" className="text-sm p-3 rounded bg-surface-container">{done}</div>}
      {editing && <ChangeFosDialog outlet={editing} employees={employees} onClose={() => setEditing(null)} onSaved={saved} />}
      {resolving && <ResolveDialog outlet={resolving} onClose={() => setResolving(null)} onSaved={saved} />}
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
      <details className="text-xs bg-surface-container-low rounded-lg border border-surface-container-highest p-3">
        <summary className="cursor-pointer font-semibold text-on-surface">What do the statuses mean?</summary>
        <dl className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          {Object.entries(STATUS_HELP).map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <dt className="shrink-0"><FosStatusBadge status={k as FosStatus} /></dt>
              <dd className="text-on-surface-variant">{v}</dd>
            </div>
          ))}
        </dl>
      </details>
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
type MappingAction = { g: FosGroup; employee_id?: string | null; not_fos?: boolean; label: string };

const GroupRow: React.FC<{ g: FosGroup; employees: Employee[]; onAsk: (a: MappingAction) => void; busy: boolean }> = ({ g, employees, onAsk, busy }) => {
  // Nothing is pre-selected: a suggestion is offered, never applied or chosen on the accountant's behalf.
  const [pick, setPick] = useState(g.employee_id ?? '');
  const nameOf = (id: string) => employees.find((e) => e.id === id)?.full_name ?? 'this employee';
  return (
    <tr className="border-t border-surface-container-highest align-top">
      <td className="px-3 py-2"><div className="font-medium">{g.group_name}</div>
        {g.suggested_employee_name && g.status === 'UNMAPPED' && g.suggested_employee_id && (
          <div className="text-xs text-on-surface-variant">
            Possible match: {g.suggested_employee_name} ({g.suggestion_basis}){' '}
            <button type="button" className="text-primary underline cursor-pointer" onClick={() => setPick(g.suggested_employee_id!)}>
              Use this
            </button>
          </div>
        )}</td>
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
          <Button size="sm" disabled={!pick || busy || pick === g.employee_id}
            onClick={() => onAsk({ g, employee_id: pick, label: `Map "${g.group_name}" to ${nameOf(pick)}` })}>Map</Button>
          <Button size="sm" variant="secondary" disabled={busy || g.status === 'NOT_FOS'}
            onClick={() => onAsk({ g, not_fos: true, label: `Mark "${g.group_name}" as not a FOS group` })}>Not a FOS group</Button>
          {g.status !== 'UNMAPPED' && <Button size="sm" variant="secondary" disabled={busy}
            onClick={() => onAsk({ g, label: `Unmap "${g.group_name}"` })}>Unmap</Button>}
        </div>
      </td>
    </tr>
  );
};

/** What a mapping decision will do, said before it is done. */
const consequence = (a: MappingAction, syncOn: boolean): string[] => {
  const n = a.g.outlets;
  const out: string[] = [];
  if (a.employee_id) {
    out.push(`The ${n} outlet${n === 1 ? '' : 's'} whose Tally ledger is in this group will have this employee as FOS.`);
    out.push(syncOn ? 'This is applied straight away for this group only.' : 'It is applied when FOS synchronisation is switched on for this server.');
  } else if (a.not_fos) {
    out.push('Outlets in this group get no FOS from Tally (the group is not a salesperson, e.g. "Sundry Debtors").');
  } else {
    out.push('The group goes back to "needs a decision". Its outlets keep the access they have until it is mapped again.');
  }
  out.push('Assignments of other groups are not touched. Nothing changes in Tally. The decision is recorded in the Change log.');
  return out;
};

const GroupsTab: React.FC<{ employees: Employee[]; onChanged: () => void; syncOn: boolean }> = ({ employees, onChanged, syncOn }) => {
  const [groups, setGroups] = useState<FosGroup[]>([]);
  const [filter, setFilter] = useState<'ALL' | 'UNMAPPED'>('UNMAPPED');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [ask, setAsk] = useState<MappingAction | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    setLoading(true);
    apiClient.getFosGroups().then((g) => { setGroups(g); setError(null); }).catch((e) => setError(errMsg(e))).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);
  const confirm = async () => {
    if (!ask) return;
    setBusy(true);
    try {
      await apiClient.mapFosGroup(ask.g.id, ask.employee_id ? { employee_id: ask.employee_id } : ask.not_fos ? { not_fos: true } : {});
      setDone(`${ask.label}: saved and recorded in the Change log.`);
      setAsk(null);
      load();
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const shown = filter === 'UNMAPPED' ? groups.filter((g) => g.status === 'UNMAPPED') : groups;
  return (
    <div className="space-y-space-4" id="fos-group-mapping">
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {done && <div role="status" className="text-sm p-3 rounded bg-surface-container">{done}</div>}
      <p className="text-sm text-on-surface-variant">
        In Tally every FOS has ledger groups (for example &quot;Raunak Usha&quot; and &quot;Raunak ZBR&quot;). Tell FieldTrack which
        employee each group stands for, once; after that every outlet the accountant puts in that group follows automatically.
        Groups that are not a salesperson (for example &quot;Sundry Debtors&quot;) are marked &quot;Not a FOS group&quot;. FieldTrack never maps a
        group on a guess: a possible match is only offered, and every decision is confirmed first.
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
            {!loading && !error && shown.length === 0 && <tr><td colSpan={5} className="px-3 py-4 text-on-surface-variant">Every Tally group has been decided.</td></tr>}
            {shown.map((g) => <GroupRow key={`${g.id}-${g.status}-${g.employee_id}`} g={g} employees={employees} onAsk={setAsk} busy={busy} />)}
          </tbody>
        </table>
      </div>
      {ask && (
        <Modal isOpen onClose={() => !busy && setAsk(null)} title="Confirm FOS group mapping">
          <div className="space-y-3 text-sm">
            <p className="font-semibold text-on-surface">{ask.label}?</p>
            <ul className="list-disc pl-5 space-y-1 text-on-surface-variant">
              {consequence(ask, syncOn).map((t) => <li key={t}>{t}</li>)}
            </ul>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setAsk(null)} disabled={busy}>Cancel</Button>
              <Button onClick={confirm} isLoading={busy}>Confirm</Button>
            </div>
          </div>
        </Modal>
      )}
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
    try {
      const r = await apiClient.runFosSync(false);
      const counts = ((r.summary as { counts?: Record<string, number> } | null)?.counts ?? {}) as Record<string, number>;
      const parts = Object.entries(counts).filter(([, n]) => n).map(([k, n]) => `${RECON_LABELS[k]?.split(':')[0] ?? k}: ${n}`);
      setNote(`Synchronised with Tally. ${parts.length ? parts.join(' · ') : 'Nothing needed to change.'}`);
      onChanged();
      await check();
    }
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
        actions={
          <Button icon={Users} onClick={() => setTab('groups')} data-testid="manage-fos-mapping">
            Manage FOS Group Mapping{unmapped > 0 ? ` (${unmapped} to map)` : ''}
          </Button>
        }
      />
      <details open className="mb-space-4 rounded-xl border border-surface-container-highest bg-surface p-4 text-sm" data-testid="fos-explainer">
        <summary className="cursor-pointer font-semibold text-on-surface flex items-center gap-2">
          <Info className="w-4 h-4 text-primary" /> How FOS assignment works
        </summary>
        <ul className="mt-3 space-y-2 text-on-surface-variant list-disc pl-5">
          <li><strong className="text-on-surface">Tally decides.</strong> Each customer ledger in Tally sits under a parent group. That group is
            the FOS: a ledger under &quot;Raunak Usha&quot; belongs to Raunak.</li>
          <li><strong className="text-on-surface">To move an outlet to another FOS,</strong> the accountant moves its ledger to the other FOS&apos;s
            group in Tally (Alter ledger, change &quot;Under&quot;). At the next Tally sync FieldTrack moves the outlet, and the move appears in the
            Change log with the old and new FOS.</li>
          <li><strong className="text-on-surface">Changing one outlet here (&quot;Change FOS&quot;):</strong> the new FOS gets the outlet in the app
            at once and the change is logged. Tally must then be updated too (move the ledger to the new FOS&apos;s group); until it is,
            FieldTrack keeps your change and shows &quot;Changed here, awaiting Tally&quot;. If Tally moves the ledger to someone else, the outlet is
            flagged as a conflict for you to decide - nothing is overwritten silently. Automatic update of Tally from FieldTrack is not
            switched on yet.</li>
          <li><strong className="text-on-surface">The one decision FieldTrack makes:</strong> which employee a Tally group stands for. Use
            &quot;Manage FOS Group Mapping&quot; for groups that are not mapped yet. Nothing is mapped automatically, and existing assignments and
            the change history are kept.</li>
        </ul>
      </details>
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
      <p className="text-xs text-on-surface-variant mb-space-3" data-testid="tab-help">{TABS.find((t) => t.key === tab)?.help}</p>
      {tab === 'outlets' && <OutletsTab employees={fieldStaff} groups={groupNames} />}
      {tab === 'groups' && <GroupsTab employees={fieldStaff} onChanged={loadSummary} syncOn={!!summary?.sync_enabled} />}
      {tab === 'reconciliation' && <ReconciliationTab summary={summary} onChanged={loadSummary} />}
      {tab === 'audit' && <AuditTab />}
    </div>
  );
};

export default FosAssignmentsPage;

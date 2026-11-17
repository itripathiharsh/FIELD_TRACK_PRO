import React, { useCallback, useEffect, useState } from 'react';
import { Link2, Upload, Undo2, Star, Unlink } from 'lucide-react';
import { apiClient } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { isSuperAdmin } from '../utils/roles';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { formatMoney } from '../utils/money';
import type {
  Customer,
  ImportApplyResult,
  ImportPreview,
  LedgerQueueItem,
  LedgerRead,
  LinkEventRead,
  OutletMappingQueues,
} from '../types';

type Tab = 'import' | 'review' | 'linked' | 'brand' | 'code' | 'history';
const TABS: { key: Tab; label: string }[] = [
  { key: 'import', label: 'Import proposal' },
  { key: 'review', label: 'Review queue' },
  { key: 'linked', label: 'Linked outlets' },
  { key: 'brand', label: 'Missing brand' },
  { key: 'code', label: 'Missing outlet code' },
  { key: 'history', label: 'History' },
];

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed');

/** Outlet search used to pick the physical shop a ledger belongs to. */
const OutletPicker: React.FC<{ onPick: (c: Customer) => void; excludeId?: string }> = ({ onPick, excludeId }) => {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<Customer[]>([]);
  const search = async () => {
    if (!q.trim()) return;
    const res = await apiClient.getCustomersPaginated({ search: q.trim(), limit: 20 });
    setResults(res.items.filter((c) => c.id !== excludeId && !c.merged_into_customer_id));
  };
  return (
    <div className="space-y-1">
      <div className="flex gap-2">
        <Input aria-label="Search outlet" placeholder="Search outlet by name or code" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button variant="secondary" onClick={search}>Search</Button>
      </div>
      {results.map((c) => (
        <button
          key={c.id}
          type="button"
          className="block w-full text-left text-xs px-2 py-1 rounded hover:bg-surface-container"
          onClick={() => onPick(c)}
        >
          {c.name} {c.outlet_code ? `· ${c.outlet_code}` : ''} {(c.ledger_count ?? 0) > 1 ? `· ${c.ledger_count} ledgers` : ''}
        </button>
      ))}
    </div>
  );
};

// ------------------------------------------------------------------ Import (preview -> apply -> revert)
const ImportTab: React.FC<{ superAdmin: boolean; onChanged: () => void }> = ({ superAdmin, onChanged }) => {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [applied, setApplied] = useState<ImportApplyResult | null>(null);
  const [revertId, setRevertId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await fn();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const canApply = !!preview && superAdmin && preview.invariants_ok && preview.errors.length === 0 && preview.links.length + preview.brand_updates.length + preview.code_updates.length > 0;

  return (
    <div className="space-y-4">
      <p className="text-xs text-on-surface-variant">
        Upload the workbook returned by the client. Only rows marked <b>Same shop? = Y</b> are applied, after this preview.
        Nothing changes until a Super Admin applies the preview; every applied batch can be reverted.
      </p>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {info && <p className="text-sm text-emerald-700" data-testid="import-info">{info}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label="Mapping workbook"
          type="file"
          accept=".xlsx"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setPreview(null);
            setApplied(null);
          }}
        />
        <Button
          variant="primary"
          disabled={!file || busy}
          onClick={() => run(async () => setPreview(await apiClient.previewOutletMappingImport(file as File)))}
        >
          <Upload className="w-4 h-4 mr-1 inline" /> Preview
        </Button>
      </div>

      {preview && (
        <div data-testid="import-preview" className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div className="p-2 rounded border">Rows: <b>{preview.rows}</b> · confirmed <b>{preview.confirmed_rows}</b> · ignored {preview.ignored_rows}</div>
            <div className="p-2 rounded border" data-testid="outlets-before-after">Outlets: <b>{preview.outlets_before}</b> → <b>{preview.outlets_after}</b></div>
            <div className="p-2 rounded border">
              Outstanding: {formatMoney(preview.totals_before.outstanding)} → {formatMoney(preview.totals_after.outstanding)}
            </div>
            <div className={`p-2 rounded border font-semibold ${preview.invariants_ok ? 'text-emerald-700' : 'text-rose-700'}`} data-testid="invariants">
              {preview.invariants_ok ? 'Totals unchanged: OK' : 'Totals would change: NOT OK'}
            </div>
          </div>
          {preview.errors.length > 0 && (
            <div className="text-xs text-rose-700" data-testid="import-errors">
              <p className="font-bold">{preview.errors.length} error(s): fix the workbook and preview again</p>
              <ul className="list-disc ml-5">
                {preview.errors.slice(0, 50).map((e, i) => (
                  <li key={i}>Row {e.row}: {e.message}</li>
                ))}
              </ul>
            </div>
          )}
          {preview.warnings.length > 0 && (
            <ul className="text-xs text-amber-700 list-disc ml-5" data-testid="import-warnings">
              {preview.warnings.slice(0, 50).map((w, i) => (
                <li key={i}>{typeof w === 'string' ? w : `Row ${w.row}: ${w.message}`}</li>
              ))}
            </ul>
          )}
          <p className="text-xs">
            {preview.links.length} ledger link(s), {preview.brand_updates.length} brand update(s), {preview.code_updates.length} outlet-code update(s).
          </p>
          {preview.links.length > 0 && (
            <div className="max-h-72 overflow-auto border rounded">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low"><tr><th className="text-left px-2 py-1">Ledger</th><th className="text-left px-2 py-1">To shop</th></tr></thead>
                <tbody>
                  {preview.links.slice(0, 500).map((l) => (
                    <tr key={l.ledger_id} className="border-t"><td className="px-2 py-1">{l.ledger_name}</td><td className="px-2 py-1">{l.to_outlet_id_label}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {superAdmin ? (
            <Button
              variant="primary"
              disabled={!canApply || busy}
              onClick={() =>
                run(async () => {
                  const r = await apiClient.applyOutletMappingImport(preview.preview_id);
                  setApplied(r);
                  setInfo(`Applied ${r.applied} change(s). Batch ${r.batch_id}`);
                  onChanged();
                })
              }
            >
              Apply preview
            </Button>
          ) : (
            <p className="text-xs text-on-surface-variant" data-testid="superadmin-only">Only a Super Admin can apply a mapping batch.</p>
          )}
        </div>
      )}
      {applied && <p className="text-xs font-mono" data-testid="applied-batch">Batch ID: {applied.batch_id}</p>}

      {superAdmin && (
        <div className="pt-3 border-t space-y-2">
          <p className="text-xs font-bold flex items-center gap-1"><Undo2 className="w-3.5 h-3.5" /> Revert a batch</p>
          <div className="flex gap-2">
            <Input aria-label="Batch ID to revert" placeholder="Batch ID" value={revertId} onChange={(e) => setRevertId(e.target.value)} />
            <Button
              variant="danger"
              disabled={!revertId.trim() || busy}
              onClick={() =>
                run(async () => {
                  const r = await apiClient.revertOutletMappingImport(revertId.trim());
                  setInfo(`Reverted ${r.reverted} change(s) of batch ${r.batch_id}`);
                  onChanged();
                })
              }
            >
              Revert
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

// ------------------------------------------------------------------ Review queue (new Tally ledgers)
const ReviewTab: React.FC<{ items: LedgerQueueItem[]; onChanged: () => void }> = ({ items: initial, onChanged }) => {
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kept, setKept] = useState<Set<string>>(new Set());
  const items = initial.filter((l) => !kept.has(l.id));
  if (items.length === 0) return <p className="text-xs text-on-surface-variant" data-testid="review-empty">No new Tally ledgers waiting for review.</p>;
  return (
    <div className="space-y-2">
      <p className="text-xs text-on-surface-variant">
        New debtor ledgers created in Tally appear here as their own outlet. Link one to the physical shop it belongs to; it is never linked automatically.
      </p>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {items.map((l) => (
        <div key={l.id} className="p-2 border rounded text-xs" data-testid="review-item">
          <div className="flex items-center justify-between gap-2">
            <span><b>{l.name}</b> {l.tally_outlet_code ? `· ${l.tally_outlet_code}` : ''} · {l.brand ?? 'Unbranded'} · {l.parent_group ?? ''}</span>
            <span className="flex gap-1">
              <Button variant="secondary" onClick={() => setOpen(open === l.id ? null : l.id)}>
                <Link2 className="w-3.5 h-3.5 mr-1 inline" /> Link to shop
              </Button>
              <Button
                variant="ghost"
                onClick={async () => {
                  setError(null);
                  try {
                    await apiClient.reviewLedger(l.id);
                    setKept((prev) => new Set(prev).add(l.id));
                    onChanged();
                  } catch (e) {
                    setError(errMsg(e));
                  }
                }}
              >
                Keep as separate outlet
              </Button>
            </span>
          </div>
          {open === l.id && (
            <div className="mt-2">
              <OutletPicker
                excludeId={l.customer_id}
                onPick={async (c) => {
                  try {
                    await apiClient.linkLedger(l.id, c.id);
                    setOpen(null);
                    onChanged();
                  } catch (e) {
                    setError(errMsg(e));
                  }
                }}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

// ------------------------------------------------------------------ Linked outlets (unlink / primary / rename)
const LinkedTab: React.FC<{ count: number; onChanged: () => void }> = ({ count, onChanged }) => {
  const [q, setQ] = useState('');
  const [outlets, setOutlets] = useState<Customer[]>([]);
  const [selected, setSelected] = useState<Customer | null>(null);
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    const res = await apiClient.getCustomersPaginated({ search: q.trim() || undefined, limit: 50 });
    setOutlets(res.items.filter((c) => (c.ledger_count ?? 0) > 1));
  };
  const open = async (id: string) => {
    const c = await apiClient.getCustomerById(id);
    setSelected(c);
    setName(c.name);
  };
  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      if (selected) await open(selected.id);
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    }
  };
  return (
    <div className="space-y-3">
      <p className="text-xs text-on-surface-variant">{count} outlet(s) currently have more than one Tally ledger.</p>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <div className="flex gap-2">
        <Input aria-label="Search linked outlets" placeholder="Search outlet" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button variant="secondary" onClick={search}>Search</Button>
      </div>
      {outlets.map((c) => (
        <button key={c.id} type="button" className="block text-left text-xs px-2 py-1 rounded hover:bg-surface-container" onClick={() => open(c.id)}>
          {c.name} · {c.ledger_count} ledgers
        </button>
      ))}
      {selected && (
        <div className="p-3 border rounded space-y-2" data-testid="linked-outlet">
          <div className="flex gap-2 items-end">
            <Input aria-label="Outlet name" label="Outlet name" value={name} onChange={(e) => setName(e.target.value)} />
            <Button variant="secondary" disabled={!name.trim() || name === selected.name} onClick={() => act(() => apiClient.renameOutlet(selected.id, name.trim()))}>
              Rename
            </Button>
          </div>
          {(selected.ledgers ?? []).map((l: LedgerRead) => (
            <div key={l.id} className="flex items-center justify-between text-xs border-t pt-1">
              <span>
                {l.is_primary && <Star className="w-3 h-3 inline text-amber-500" aria-label="Primary ledger" />} {l.name} · {l.brand ?? 'Unbranded'}
              </span>
              <span className="flex gap-1">
                {!l.is_primary && (
                  <Button variant="ghost" onClick={() => act(() => apiClient.setPrimaryLedger(l.id))}>Set primary</Button>
                )}
                <Button variant="ghost" onClick={() => act(() => apiClient.unlinkLedger(l.id))}>
                  <Unlink className="w-3 h-3 mr-1 inline" /> Unlink
                </Button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ------------------------------------------------------------------ Missing brand / outlet code
const FillTab: React.FC<{
  items: LedgerQueueItem[];
  kind: 'brand' | 'code';
  onChanged: () => void;
}> = ({ items, kind, onChanged }) => {
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  if (items.length === 0) return <p className="text-xs text-on-surface-variant">Nothing missing.</p>;
  return (
    <div className="space-y-1">
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <p className="text-xs text-on-surface-variant">
        {kind === 'brand'
          ? 'Tally gives no brand for these ledgers. Set the brand supplied by the client (recorded as a manual override; Tally data is not changed).'
          : 'These outlets have no outlet/DMS code. Set it only where the client supplied one; codes are never guessed.'}
      </p>
      {items.map((l) => (
        <div key={l.id} className="flex items-center gap-2 text-xs" data-testid={`fill-${kind}`}>
          <span className="flex-1 truncate">{l.name}</span>
          <Input
            aria-label={`${kind === 'brand' ? 'Brand' : 'Outlet code'} for ${l.name}`}
            value={values[l.id] ?? ''}
            onChange={(e) => setValues({ ...values, [l.id]: e.target.value })}
          />
          <Button
            variant="secondary"
            disabled={!(values[l.id] ?? '').trim()}
            onClick={async () => {
              setError(null);
              try {
                const v = (values[l.id] ?? '').trim();
                if (kind === 'brand') await apiClient.setLedgerBrand(l.id, v);
                else await apiClient.setOutletCode(l.customer_id, v);
                onChanged();
              } catch (e) {
                setError(errMsg(e));
              }
            }}
          >
            Save
          </Button>
        </div>
      ))}
    </div>
  );
};

// ------------------------------------------------------------------ History
const HistoryTab: React.FC = () => {
  const [batch, setBatch] = useState('');
  const [events, setEvents] = useState<LinkEventRead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async (b?: string) => {
    try {
      setEvents(await apiClient.getOutletMappingEvents({ batch_id: b || undefined, limit: 200 }));
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="space-y-2">
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <div className="flex gap-2">
        <Input aria-label="Filter by batch ID" placeholder="Batch ID (optional)" value={batch} onChange={(e) => setBatch(e.target.value)} />
        <Button variant="secondary" onClick={() => load(batch.trim())}>Filter</Button>
      </div>
      <table className="w-full text-xs">
        <thead className="bg-surface-container-low">
          <tr><th className="text-left px-2 py-1">When</th><th className="text-left px-2 py-1">Action</th><th className="text-left px-2 py-1">Ledger</th><th className="text-left px-2 py-1">By</th><th className="text-left px-2 py-1">Batch</th><th className="text-left px-2 py-1">Note</th></tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={ev.id} className="border-t" data-testid="event-row">
              <td className="px-2 py-1 whitespace-nowrap">{new Date(ev.created_at).toLocaleString('en-IN')}</td>
              <td className="px-2 py-1">{ev.action}</td>
              <td className="px-2 py-1">{ev.ledger_name ?? '—'}</td>
              <td className="px-2 py-1">{ev.actor ?? '—'}</td>
              <td className="px-2 py-1 font-mono">{ev.batch_id ?? '—'}</td>
              <td className="px-2 py-1">{ev.note ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

/**
 * 2.1.0 Outlet mapping: one physical shop = one outlet, with its Tally brand ledgers linked to it.
 * Links come only from client-confirmed rows (import) or explicit admin actions; never automatic.
 */
export const OutletMappingPage: React.FC = () => {
  const { user } = useAuth();
  const superAdmin = isSuperAdmin(user);
  const [tab, setTab] = useState<Tab>('import');
  const [queues, setQueues] = useState<OutletMappingQueues | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadQueues = useCallback(async () => {
    try {
      setQueues(await apiClient.getOutletMappingQueues());
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => {
    void loadQueues();
  }, [loadQueues]);

  const counts: Partial<Record<Tab, number>> = {
    review: queues?.new_unreviewed.length,
    brand: queues?.missing_brand.length,
    code: queues?.missing_code.length,
    linked: queues?.linked_outlets,
  };

  return (
    <div>
      <PageHeader
        title="Outlet Mapping"
        subtitle="One physical shop = one outlet. Link the shop's Tally brand ledgers; each ledger keeps its own Tally records."
        breadcrumbs={[{ label: 'Customers' }, { label: 'Outlet Mapping' }]}
      />
      {error && <ErrorBanner message={error} onRetry={loadQueues} onDismiss={() => setError(null)} />}
      <div role="tablist" className="flex flex-wrap gap-1 mb-4">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${tab === t.key ? 'bg-primary-container text-on-primary-container' : 'bg-surface-container-low text-on-surface-variant'}`}
          >
            {t.label}
            {counts[t.key] !== undefined && <span className="ml-1 opacity-80">({counts[t.key]})</span>}
          </button>
        ))}
      </div>
      <Card className="p-4">
        {tab === 'import' && <ImportTab superAdmin={superAdmin} onChanged={loadQueues} />}
        {tab === 'review' && <ReviewTab items={queues?.new_unreviewed ?? []} onChanged={loadQueues} />}
        {tab === 'linked' && <LinkedTab count={queues?.linked_outlets ?? 0} onChanged={loadQueues} />}
        {tab === 'brand' && <FillTab kind="brand" items={queues?.missing_brand ?? []} onChanged={loadQueues} />}
        {tab === 'code' && <FillTab kind="code" items={queues?.missing_code ?? []} onChanged={loadQueues} />}
        {tab === 'history' && <HistoryTab />}
      </Card>
    </div>
  );
};

export default OutletMappingPage;

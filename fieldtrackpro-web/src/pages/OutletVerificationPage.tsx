import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Camera, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { OutletProofReviewCard } from '../components/outlet-proofs/OutletProofReviewCard';
import { OutletPhotoLightbox } from '../components/outlet-proofs/OutletProofImage';
import { apiClient } from '../api/client';
import { OutletProof, OutletProofKind, OutletProofStatusFilter } from '../types';
import { isStaleProofError, outletProofErrorMessage } from '../utils/outletProof';

const PAGE_SIZE = 10;
const STATUS_FILTERS: { value: OutletProofStatusFilter; label: string }[] = [
  { value: 'PENDING', label: 'Pending' },
  { value: 'CONFIRMED', label: 'Confirmed' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'ALL', label: 'All' },
];

/** Admin review queue for live outlet proofs (photo + GPS captured at the same click). */
export const OutletVerificationPage: React.FC = () => {
  const [status, setStatus] = useState<OutletProofStatusFilter>('PENDING');
  const [kind, setKind] = useState<OutletProofKind | ''>('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<OutletProof[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  const [lightbox, setLightbox] = useState<OutletProof | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiClient.getOutletProofs({
        status,
        kind: kind || undefined,
        skip: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load outlet proofs');
    } finally {
      setIsLoading(false);
    }
  }, [status, kind, page]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((p) =>
      [p.customer_name, p.prospect_name, p.customer_outlet_code, p.submitted_by_name]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [items, search]);

  const candidatesFor = (p: OutletProof): OutletProof[] =>
    p.customer_id
      ? items.filter((o) => o.id !== p.id && o.customer_id === p.customer_id && o.status === 'PENDING')
      : [];

  const handleApprove = async (p: OutletProof): Promise<string | null> => {
    try {
      await apiClient.approveOutletProof(p.id);
      setToast({ kind: 'success', text: `Location and photo approved for ${p.customer_name || p.prospect_name || 'outlet'}.` });
      await load();
      return null;
    } catch (err) {
      if (isStaleProofError(err)) void load();
      return outletProofErrorMessage(err);
    }
  };

  const handleReject = async (p: OutletProof, reason: string): Promise<string | null> => {
    try {
      await apiClient.rejectOutletProof(p.id, reason);
      setToast({ kind: 'success', text: `Proof rejected for ${p.customer_name || p.prospect_name || 'outlet'}.` });
      await load();
      return null;
    } catch (err) {
      if (isStaleProofError(err)) void load();
      return outletProofErrorMessage(err);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-space-6 max-w-7xl mx-auto">
      <PageHeader
        title="Outlet Verification"
        subtitle="Review live outlet photos together with the GPS point captured at the same moment."
        actions={
          <Button variant="outline" size="md" icon={RefreshCw} onClick={() => void load()} isLoading={isLoading}>
            Refresh
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 bg-surface-container p-1 rounded-lg border border-outline-variant" role="group" aria-label="Status filter">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-pressed={status === f.value}
              onClick={() => {
                setStatus(f.value);
                setPage(1);
              }}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors cursor-pointer ${
                status === f.value ? 'bg-surface text-primary shadow-xs' : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <select
          aria-label="Kind filter"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as OutletProofKind | '');
            setPage(1);
          }}
          className="text-xs p-2 rounded border border-outline bg-surface text-on-surface"
        >
          <option value="">All kinds</option>
          <option value="INITIAL">Initial</option>
          <option value="CONFIRMATION">Confirmation</option>
          <option value="CHANGE_REQUEST">Change request</option>
        </select>
        <input
          type="search"
          aria-label="Search outlet"
          placeholder="Search this page by outlet, code or employee..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[220px] text-xs p-2 rounded border border-outline bg-surface text-on-surface"
        />
      </div>

      {toast && (
        <div
          role="status"
          className={`p-3 rounded-lg text-sm flex items-center justify-between gap-3 border ${
            toast.kind === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <span>{toast.text}</span>
          <button type="button" onClick={() => setToast(null)} className="text-xs font-bold cursor-pointer">
            Dismiss
          </button>
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      {isLoading && items.length === 0 ? (
        <div className="flex items-center justify-center h-48" role="status" aria-label="Loading outlet proofs">
          <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
        </div>
      ) : !error && visible.length === 0 ? (
        <EmptyState
          icon={Camera}
          title={status === 'PENDING' ? 'Nothing to review' : 'No outlet proofs found'}
          subtitle={
            search
              ? 'No proof on this page matches your search.'
              : status === 'PENDING'
                ? 'All live outlet photos have been reviewed.'
                : 'Try a different status or kind filter.'
          }
        />
      ) : (
        <div className="space-y-4" aria-busy={isLoading}>
          {visible.map((p) => (
            <OutletProofReviewCard
              key={p.id}
              proof={p}
              candidates={candidatesFor(p)}
              onOpenPhoto={setLightbox}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-xs text-on-surface-variant">
          <span>
            Page {page} of {totalPages} ({total} proofs)
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" icon={ChevronLeft} disabled={page <= 1 || isLoading} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" icon={ChevronRight} iconPosition="right" disabled={page >= totalPages || isLoading} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}

      <OutletPhotoLightbox
        proofId={lightbox?.id ?? null}
        title={lightbox ? lightbox.customer_name || lightbox.prospect_name || undefined : undefined}
        onClose={() => setLightbox(null)}
      />
    </div>
  );
};

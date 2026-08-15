import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Download, FileText } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { Textarea } from '../components/ui/Textarea';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Modal } from '../components/ui/Modal';
import { StatusBadge } from '../components/ui/StatusBadge';
import { DataTable, Column } from '../components/ui/DataTable';
import { apiClient } from '../api/client';
import { Payment, PaymentStatus } from '../types';

const formatCurrency = (value: string): string => `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

/**
 * Admin/accountant payment review queue.
 *
 * Design note: the product spec discusses "accountant" review throughout,
 * but there is no dedicated ACCOUNTANT login role in this system (only
 * ADMIN/EMPLOYEE) and the spec itself uses "Admin / Accountant" more or less
 * interchangeably for this workflow. Rather than introduce a new role end to
 * end (backend enum, frontend type, route guards, nav) on an ambiguous cue,
 * this page is gated the same way every other admin-only page already is.
 * Adding a dedicated role later is a contained, additive change if the
 * client confirms they want a separate accounting login.
 */
export const PaymentReviewPage: React.FC = () => {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [statusFilter, setStatusFilter] = useState<PaymentStatus | ''>('PENDING_VERIFICATION');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Payment | null>(null);
  const [proofUrls, setProofUrls] = useState<Record<string, string>>({});
  const [rejectionReason, setRejectionReason] = useState('');
  const [isActing, setIsActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getPaymentReviewQueue(statusFilter || undefined);
      setPayments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load review queue');
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  // P1-11: fetch proof preview object URLs for whichever payment is open,
  // and revoke every one of them on cleanup (closing the modal, opening a
  // different payment, or unmounting) - mirrors the same cancelled-guard +
  // revoke-on-cleanup pattern already used by MediaThumbnail.tsx. Previously
  // these URLs were fetched once (in openDetail) and never revoked at all,
  // so every payment reviewed in an admin session permanently retained its
  // proof photo(s) in memory.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const createdUrls: string[] = [];

    void (async () => {
      for (const proof of selected.proofs) {
        try {
          const url = await apiClient.getPaymentProofObjectUrl(proof.id);
          if (cancelled) {
            URL.revokeObjectURL(url);
            continue;
          }
          createdUrls.push(url);
          setProofUrls((prev) => ({ ...prev, [proof.id]: url }));
        } catch {
          // Preview unavailable - download button still works via a fresh fetch.
        }
      }
    })();

    return () => {
      cancelled = true;
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
      setProofUrls({});
    };
  }, [selected]);

  const openDetail = (payment: Payment) => {
    setSelected(payment);
    setRejectionReason('');
    setActionError(null);
  };

  const handleVerify = async () => {
    if (!selected) return;
    setIsActing(true);
    setActionError(null);
    try {
      await apiClient.verifyPayment(selected.id);
      setSelected(null);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to verify payment');
    } finally {
      setIsActing(false);
    }
  };

  const handleReject = async () => {
    if (!selected) return;
    if (!rejectionReason.trim()) {
      setActionError('A rejection reason is required.');
      return;
    }
    setIsActing(true);
    setActionError(null);
    try {
      await apiClient.rejectPayment(selected.id, rejectionReason);
      setSelected(null);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to reject payment');
    } finally {
      setIsActing(false);
    }
  };

  const handleDownloadProof = async (proofId: string, filename: string) => {
    try {
      const cachedUrl = proofUrls[proofId];
      const url = cachedUrl ?? (await apiClient.getPaymentProofObjectUrl(proofId));
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Only revoke a URL we just created for this one-off download - the
      // cached one is still owned by (and revoked by) the effect above.
      if (!cachedUrl) URL.revokeObjectURL(url);
    } catch {
      setActionError('Failed to download proof');
    }
  };

  const columns: Column<Payment>[] = [
    { header: 'Outlet', accessor: (p) => <span className="font-medium">{p.customer_name || p.customer_id.slice(0, 8)}</span> },
    { header: 'Employee', accessor: (p) => p.employee_name || p.employee_id.slice(0, 8) },
    { header: 'Amount', accessor: (p) => formatCurrency(p.amount) },
    { header: 'Method', accessor: (p) => p.payment_method },
    { header: 'Date', accessor: (p) => p.payment_date },
    { header: 'Status', accessor: (p) => <StatusBadge status={p.status} size="sm" /> },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader title="Payment Collections" subtitle="Review, verify, or reject field collections before they count toward outlet balances." />

      {error && <ErrorBanner message={error} onRetry={load} />}

      <div className="flex items-center gap-space-3 max-w-xs">
        <Select
          label="Status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as PaymentStatus | '')}
        >
          <option value="PENDING_VERIFICATION">Pending</option>
          <option value="VERIFIED">Verified</option>
          <option value="REJECTED">Rejected</option>
          <option value="">All</option>
        </Select>
      </div>

      <DataTable
        columns={columns}
        data={payments}
        isLoading={isLoading}
        emptyMessage="No collections in this status"
        onRowClick={(p) => openDetail(p)}
      />

      <Modal isOpen={!!selected} onClose={() => setSelected(null)} title="Collection Detail" size="lg">
        {selected && (
          <div className="space-y-space-4">
            {actionError && <ErrorBanner message={actionError} />}

            <div className="grid grid-cols-2 gap-space-3 text-sm">
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Outlet</p>
                <p className="font-medium">{selected.customer_name || '—'}</p>
                {selected.outlet_code && <p className="text-xs text-on-surface-variant font-mono">{selected.outlet_code}</p>}
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Territory</p>
                <p className="font-medium">{selected.territory_name || '—'}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Employee</p>
                <p className="font-medium">{selected.employee_name || '—'}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Amount</p>
                <p className="font-medium">{formatCurrency(selected.amount)}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Method</p>
                <p className="font-medium">{selected.payment_method}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Payment Date</p>
                <p className="font-medium">{selected.payment_date}</p>
              </div>
              {selected.utr_reference && (
                <div>
                  <p className="text-on-surface-variant font-caption text-xs uppercase">UTR / Reference</p>
                  <p className="font-medium">{selected.utr_reference}</p>
                </div>
              )}
              {selected.cheque_number && (
                <div>
                  <p className="text-on-surface-variant font-caption text-xs uppercase">Cheque</p>
                  <p className="font-medium">{selected.cheque_number} {selected.cheque_bank_name ? `· ${selected.cheque_bank_name}` : ''}</p>
                </div>
              )}
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Status</p>
                <StatusBadge status={selected.status} size="sm" />
              </div>
              {selected.notes && (
                <div className="col-span-2">
                  <p className="text-on-surface-variant font-caption text-xs uppercase">Notes</p>
                  <p className="font-medium">{selected.notes}</p>
                </div>
              )}
              {selected.rejection_reason && (
                <div className="col-span-2">
                  <p className="text-error font-caption text-xs uppercase">Rejection Reason</p>
                  <p className="font-medium text-error">{selected.rejection_reason}</p>
                </div>
              )}
            </div>

            <div>
              <p className="text-on-surface-variant font-caption text-xs uppercase mb-space-2">Proof of Payment</p>
              {selected.proofs.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No proof was attached to this collection.</p>
              ) : (
                <div className="grid grid-cols-2 gap-space-3">
                  {selected.proofs.map((proof) => (
                    <div key={proof.id} className="border border-outline-variant rounded-lg p-space-2 space-y-space-2">
                      {proofUrls[proof.id] ? (
                        (proof.original_filename || '').toLowerCase().endsWith('.pdf') ? (
                          <a href={proofUrls[proof.id]} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-primary text-sm">
                            <FileText className="w-4 h-4" /> View PDF
                          </a>
                        ) : (
                          <img src={proofUrls[proof.id]} alt={proof.original_filename || 'proof'} className="w-full h-32 object-cover rounded-md" />
                        )
                      ) : (
                        <div className="w-full h-32 bg-surface-container-low rounded-md flex items-center justify-center text-on-surface-variant text-xs">
                          Preview unavailable
                        </div>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        icon={Download}
                        className="w-full"
                        onClick={() => void handleDownloadProof(proof.id, proof.original_filename || 'proof')}
                      >
                        Download
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {selected.status === 'PENDING_VERIFICATION' && (
              <div className="space-y-space-3 pt-space-2 border-t border-surface-container-highest">
                <Textarea
                  label="Rejection reason (required to reject)"
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  rows={2}
                />
                <div className="flex gap-space-3">
                  <Button variant="danger" icon={XCircle} className="flex-1" isLoading={isActing} onClick={() => void handleReject()}>
                    Reject
                  </Button>
                  <Button variant="primary" icon={CheckCircle2} className="flex-1" isLoading={isActing} onClick={() => void handleVerify()}>
                    Verify
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

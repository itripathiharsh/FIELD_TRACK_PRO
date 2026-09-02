import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, XCircle, Download, FileText, Edit2, Save } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Textarea } from '../components/ui/Textarea';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Modal } from '../components/ui/Modal';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PaymentMethodBadge } from '../components/ui/PaymentMethodBadge';
import { DataTable, Column } from '../components/ui/DataTable';
import { apiClient } from '../api/client';
import { Payment, PaymentStatus, BrandAllocationInput } from '../types';

const formatCurrency = (value: string | number): string =>
  `₹${Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

/**
 * Admin/accountant payment review queue with Brand-Wise Allocation breakdown & adjustment.
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

  // Admin allocation correction state
  const [isEditingAllocations, setIsEditingAllocations] = useState(false);
  const [editAllocations, setEditAllocations] = useState<{ brand: string; amount: string }[]>([]);
  const [isSavingAllocations, setIsSavingAllocations] = useState(false);

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

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const createdUrls: string[] = [];

    void (async () => {
      for (const proof of selected.proofs || []) {
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
    setIsEditingAllocations(false);
    setEditAllocations(
      (payment.allocations || []).map((a) => ({
        brand: a.brand,
        amount: a.allocated_amount,
      })),
    );
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
      if (!cachedUrl) URL.revokeObjectURL(url);
    } catch {
      setActionError('Failed to download proof');
    }
  };

  const handleSaveAllocations = async () => {
    if (!selected) return;
    setActionError(null);

    const parsed: BrandAllocationInput[] = [];
    let sum = 0;
    for (const alloc of editAllocations) {
      const amt = parseFloat(alloc.amount || '0');
      if (Number.isNaN(amt) || amt <= 0) {
        setActionError(`Allocation for ${alloc.brand} must be greater than zero.`);
        return;
      }
      parsed.push({ brand: alloc.brand.trim(), amount: amt });
      sum += amt;
    }

    const totalAmt = parseFloat(selected.amount);
    if (Math.abs(sum - totalAmt) > 0.01) {
      setActionError(
        `Allocation sum (${formatCurrency(sum)}) must equal payment total (${formatCurrency(totalAmt)}).`,
      );
      return;
    }

    setIsSavingAllocations(true);
    try {
      const updated = await apiClient.updatePaymentAllocations(selected.id, parsed);
      setSelected(updated);
      setIsEditingAllocations(false);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update brand allocations');
    } finally {
      setIsSavingAllocations(false);
    }
  };

  const columns: Column<Payment>[] = [
    { header: 'Outlet', accessor: (p) => <span className="font-medium">{p.customer_name || p.customer_id.slice(0, 8)}</span> },
    { header: 'Employee', accessor: (p) => p.employee_name || p.employee_id.slice(0, 8) },
    { header: 'Amount', accessor: (p) => formatCurrency(p.amount) },
    {
      header: 'Brand Allocation',
      accessor: (p) =>
        p.allocations && p.allocations.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {p.allocations.map((a) => (
              <span key={a.id} className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium bg-surface-container-highest text-on-surface">
                {a.brand}: {formatCurrency(a.allocated_amount)}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-xs text-on-surface-variant">General</span>
        ),
    },
    {
      header: 'Method',
      accessor: (p) => (
        <PaymentMethodBadge
          method={p.payment_method}
          chequeNumber={p.cheque_number}
        />
      ),
    },
    { header: 'Date', accessor: (p) => p.payment_date },
    { header: 'Status', accessor: (p) => <StatusBadge status={p.status} size="sm" /> },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Payment Collections"
        subtitle="Review, verify, or reject field collections before they count toward outlet balances."
      />

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
                <p className="text-on-surface-variant font-caption text-xs uppercase">Total Payment Amount</p>
                <p className="font-bold text-base text-primary">{formatCurrency(selected.amount)}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Method</p>
                <div className="mt-1">
                  <PaymentMethodBadge
                    method={selected.payment_method}
                    size="md"
                    chequeNumber={selected.cheque_number}
                  />
                </div>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Payment Date</p>
                <p className="font-medium">{selected.payment_date}</p>
              </div>
              {selected.utr_reference && (
                <div>
                  <p className="text-on-surface-variant font-caption text-xs uppercase">UTR / Reference</p>
                  <p className="font-medium font-mono">{selected.utr_reference}</p>
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
                  <p className="font-medium whitespace-pre-wrap">{selected.notes}</p>
                </div>
              )}
              {selected.rejection_reason && (
                <div className="col-span-2">
                  <p className="text-error font-caption text-xs uppercase">Rejection Reason</p>
                  <p className="font-medium text-error">{selected.rejection_reason}</p>
                </div>
              )}
            </div>

            {/* Brand Allocation Breakdown Card */}
            <div className="bg-surface-container-low p-space-3 rounded-xl border border-outline-variant">
              <div className="flex items-center justify-between mb-space-2">
                <p className="text-xs font-bold uppercase tracking-wider text-primary">
                  Brand Allocation Breakdown
                </p>
                {selected.status === 'PENDING_VERIFICATION' && (
                  <Button
                    variant="outline"
                    size="sm"
                    icon={isEditingAllocations ? undefined : Edit2}
                    onClick={() => {
                      setIsEditingAllocations(!isEditingAllocations);
                      setActionError(null);
                    }}
                  >
                    {isEditingAllocations ? 'Cancel Edit' : 'Adjust Allocation'}
                  </Button>
                )}
              </div>

              {isEditingAllocations ? (
                <div className="space-y-space-3 pt-space-2 border-t border-outline-variant/60">
                  <p className="text-xs text-on-surface-variant">
                    Adjust amounts per brand. The sum must equal the payment total ({formatCurrency(selected.amount)}).
                  </p>
                  <div className="space-y-space-2">
                    {editAllocations.map((alloc, idx) => (
                      <div key={alloc.brand} className="flex items-center gap-space-3">
                        <span className="font-semibold text-sm w-32 truncate">{alloc.brand}</span>
                        <div className="flex-1">
                          <Input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={alloc.amount}
                            onChange={(e) => {
                              const newAllocs = [...editAllocations];
                              newAllocs[idx] = { ...newAllocs[idx], amount: e.target.value };
                              setEditAllocations(newAllocs);
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="flex justify-end gap-space-2 pt-space-2">
                    <Button
                      variant="primary"
                      size="sm"
                      icon={Save}
                      isLoading={isSavingAllocations}
                      onClick={() => void handleSaveAllocations()}
                    >
                      Save Adjusted Allocation
                    </Button>
                  </div>
                </div>
              ) : selected.allocations && selected.allocations.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-2 pt-space-2 border-t border-outline-variant/40">
                  {selected.allocations.map((a) => (
                    <div key={a.id} className="flex items-center justify-between bg-surface p-space-2 rounded-lg border border-outline-variant/60">
                      <span className="font-semibold text-sm text-on-surface">{a.brand}</span>
                      <span className="font-mono font-bold text-sm text-primary">{formatCurrency(a.allocated_amount)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-on-surface-variant pt-space-1">
                  Single on-account payment without brand split.
                </p>
              )}
            </div>

            {/* Proofs */}
            <div>
              <p className="text-on-surface-variant font-caption text-xs uppercase mb-space-2">Proof of Payment</p>
              {!selected.proofs || selected.proofs.length === 0 ? (
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

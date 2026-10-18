import React, { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, XCircle, Download, FileText, Edit2, Save, RefreshCw, AlertTriangle } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Textarea } from '../components/ui/Textarea';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Modal } from '../components/ui/Modal';
import { StatusBadge } from '../components/ui/StatusBadge';
import { TallyStatusBadge } from '../components/ui/TallyStatusBadge';
import { PaymentMethodBadge } from '../components/ui/PaymentMethodBadge';
import { DataTable, Column } from '../components/ui/DataTable';
import { apiClient } from '../api/client';
import { Payment, PaymentStatus, BrandAllocationInput, TallyStatus } from '../types';
import { formatMoney as formatCurrency, parseAmountToPaise, paiseToAmountString, clampAmountInput, normalizeAmountString } from '../utils/money';

/**
 * Admin/accountant payment review queue with Brand-Wise Allocation breakdown & adjustment.
 */
export const PaymentReviewPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const initialStuck = searchParams.get('stuck') === 'true';
  const [payments, setPayments] = useState<Payment[]>([]);
  // A "stuck" deep link (from the dashboard) only makes sense among verified payments.
  const [statusFilter, setStatusFilter] = useState<PaymentStatus | ''>(
    initialStuck ? 'VERIFIED' : 'PENDING_VERIFICATION',
  );
  const [tallyFilter, setTallyFilter] = useState<TallyStatus | ''>('');
  const [stuckOnly, setStuckOnly] = useState(initialStuck);
  const [verifyBankRef, setVerifyBankRef] = useState('');
  const [verifyBankDate, setVerifyBankDate] = useState('');
  const [verifyNote, setVerifyNote] = useState('');
  const [retryTarget, setRetryTarget] = useState<Payment | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
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
      const data = await apiClient.getPaymentReviewQueue(statusFilter || undefined, {
        tally_status: tallyFilter || undefined,
        stuck: stuckOnly || undefined,
      });
      setPayments(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load review queue');
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, tallyFilter, stuckOnly]);

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
    setVerifyBankRef('');
    setVerifyBankDate('');
    setVerifyNote('');
    setIsEditingAllocations(false);
    setEditAllocations(
      (payment.allocations || []).map((a) => ({
        brand: a.brand,
        amount: normalizeAmountString(a.allocated_amount),
      })),
    );
  };

  const handleVerify = async () => {
    if (!selected) return;
    setIsActing(true);
    setActionError(null);
    try {
      await apiClient.verifyPayment(selected.id, {
        ...(verifyBankRef.trim() ? { bank_reference: verifyBankRef.trim() } : {}),
        ...(verifyBankDate ? { bank_verified_on: verifyBankDate } : {}),
        ...(verifyNote.trim() ? { verified_note: verifyNote.trim() } : {}),
      });
      setSelected(null);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to verify payment');
    } finally {
      setIsActing(false);
    }
  };

  const handleConfirmRetry = async () => {
    if (!retryTarget) return;
    setIsRetrying(true);
    setRetryError(null);
    try {
      const updated = await apiClient.retryPaymentTally(retryTarget.id);
      setPayments((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
      setSelected((prev) => (prev && prev.id === updated.id ? { ...prev, ...updated } : prev));
      setRetryTarget(null);
    } catch (err) {
      setRetryError(err instanceof Error ? err.message : 'Failed to retry the Tally post');
    } finally {
      setIsRetrying(false);
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
    let sumPaiseTotal = 0;
    for (const alloc of editAllocations) {
      const res = parseAmountToPaise(alloc.amount);
      if (!res.ok) {
        setActionError(
          res.reason === 'too_many_decimals'
            ? `Allocation for ${alloc.brand} can have at most 2 decimal places.`
            : `Allocation for ${alloc.brand} must be a valid amount greater than zero.`,
        );
        return;
      }
      if (res.paise <= 0) {
        setActionError(`Allocation for ${alloc.brand} must be greater than zero.`);
        return;
      }
      parsed.push({ brand: alloc.brand.trim(), amount: paiseToAmountString(res.paise) });
      sumPaiseTotal += res.paise;
    }

    const total = parseAmountToPaise(selected.amount);
    if (!total.ok || sumPaiseTotal !== total.paise) {
      setActionError(
        `Allocation sum (${formatCurrency(paiseToAmountString(sumPaiseTotal))}) must equal payment total (${formatCurrency(selected.amount)}).`,
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
    {
      header: 'Tally',
      accessor: (p) => {
        if (p.status !== 'VERIFIED' || !p.tally_status || p.tally_status === 'NOT_APPLICABLE') {
          return <span className="text-xs text-on-surface-variant">-</span>;
        }
        const problem = p.tally_status === 'FAILED' || p.tally_stuck;
        return (
          <div className="space-y-1 max-w-[240px]">
            <TallyStatusBadge status={p.tally_status} />
            {p.tally_status === 'POSTED' && p.tally_voucher_number && (
              <p className="text-[11px] font-mono text-on-surface-variant">Voucher {p.tally_voucher_number}</p>
            )}
            {p.tally_stuck && p.tally_status === 'AWAITING_TALLY' && (
              <p className="text-[11px] font-semibold text-error">Stuck - waiting 30+ min</p>
            )}
            {problem && p.tally_error && (
              <p className="text-[11px] text-error break-words" title={p.tally_error}>{p.tally_error}</p>
            )}
            {p.tally_status === 'FAILED' && (
              <Button
                variant="outline"
                size="sm"
                icon={RefreshCw}
                onClick={(e) => {
                  e.stopPropagation();
                  setRetryError(null);
                  setRetryTarget(p);
                }}
              >
                Retry Tally post
              </Button>
            )}
          </div>
        );
      },
    },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Payment Collections"
        subtitle="Review, verify, or reject field collections before they count toward outlet balances."
      />

      {error && <ErrorBanner message={error} onRetry={load} />}

      <div
        role="note"
        className="p-space-3 bg-primary-tint border border-primary-fixed-dim text-primary rounded-xl text-xs font-body-md"
      >
        Lifecycle: <strong>Pending verification</strong> &rarr; <strong>Verified, awaiting Tally</strong> &rarr;{' '}
        <strong>Posted to Tally</strong>. Collections submitted by field staff stay pending until an admin
        verifies them. Tally posting happens after verification, and outlet balances change only after Tally
        confirms the posting; rejected collections are never posted.
      </div>

      <div className="flex flex-wrap items-end gap-space-3">
        <div className="w-56">
        <Select
          label="Status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as PaymentStatus | '')}
        >
          <option value="PENDING_VERIFICATION">Pending verification</option>
          <option value="VERIFIED">Verified</option>
          <option value="REJECTED">Rejected</option>
          <option value="">All</option>
        </Select>
        </div>
        <div className="w-56">
          <Select
            label="Tally status"
            value={tallyFilter}
            onChange={(e) => setTallyFilter(e.target.value as TallyStatus | '')}
          >
            <option value="">All Tally statuses</option>
            <option value="AWAITING_TALLY">Verified, awaiting Tally</option>
            <option value="POSTED">Posted to Tally</option>
            <option value="FAILED">Tally post failed</option>
          </Select>
        </div>
        <label className="flex items-center gap-2 text-sm pb-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={stuckOnly}
            onChange={(e) => setStuckOnly(e.target.checked)}
          />
          Stuck only (failed or waiting 30+ min)
        </label>
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
              {selected.status === 'VERIFIED' && selected.tally_status && selected.tally_status !== 'NOT_APPLICABLE' && (
                <div className="col-span-2 space-y-1">
                  <p className="text-on-surface-variant font-caption text-xs uppercase">Tally</p>
                  <TallyStatusBadge status={selected.tally_status} />
                  {selected.tally_status === 'POSTED' && (
                    <p className="text-xs text-on-surface-variant">
                      {selected.tally_voucher_number ? `Voucher ${selected.tally_voucher_number}` : 'Posted'}
                      {selected.tally_posted_at ? ` · ${new Date(selected.tally_posted_at).toLocaleString('en-IN')}` : ''}
                    </p>
                  )}
                  {(selected.tally_status === 'FAILED' || selected.tally_stuck) && (
                    <div role="alert" className="p-space-2 rounded-lg border border-error bg-error-container text-on-error-container text-xs flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <p className="font-semibold">
                          {selected.tally_status === 'FAILED' ? 'Tally post failed' : 'Stuck: awaiting Tally for 30+ minutes'}
                        </p>
                        {selected.tally_error && <p className="break-words">{selected.tally_error}</p>}
                      </div>
                      {selected.tally_status === 'FAILED' && (
                        <Button
                          variant="outline"
                          size="sm"
                          icon={RefreshCw}
                          onClick={() => {
                            setRetryError(null);
                            setRetryTarget(selected);
                          }}
                        >
                          Retry Tally post
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              )}
              {(selected.bank_reference || selected.bank_verified_on || selected.verified_note) && (
                <div className="col-span-2">
                  <p className="text-on-surface-variant font-caption text-xs uppercase">Bank verification</p>
                  <p className="text-sm">
                    {selected.bank_reference ? `Ref ${selected.bank_reference}` : ''}
                    {selected.bank_verified_on ? ` · verified on ${selected.bank_verified_on}` : ''}
                  </p>
                  {selected.verified_note && <p className="text-xs text-on-surface-variant whitespace-pre-wrap">{selected.verified_note}</p>}
                </div>
              )}
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
                            type="text"
                            inputMode="decimal"
                            value={alloc.amount}
                            onChange={(e) => {
                              const newAllocs = [...editAllocations];
                              newAllocs[idx] = { ...newAllocs[idx], amount: clampAmountInput(e.target.value) };
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
                          <a href={proofUrls[proof.id]} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-primary text-sm">
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

            {selected.status === 'VERIFIED' && (
              <p className="text-xs text-on-surface-variant">
                Verified. Tally posting happens after verification; the outstanding balance drops only once Tally confirms the posting. Verified collections cannot be changed here.
              </p>
            )}
            {selected.status === 'REJECTED' && (
              <p className="text-xs text-error">
                Rejected. This collection will not be posted to Tally.
              </p>
            )}

            {selected.status === 'PENDING_VERIFICATION' && (
              <div className="space-y-space-3 pt-space-2 border-t border-surface-container-highest">
                <p className="text-xs text-on-surface-variant">
                  Not yet posted to Tally. Verifying makes this collection eligible for Tally posting.
                </p>
                <div className="space-y-space-2 p-space-3 rounded-xl border border-outline-variant bg-surface-container-low">
                  <p className="text-xs font-bold text-primary">Confirm the money is in the bank before verifying</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3">
                    <Input
                      label="Bank reference (optional)"
                      value={verifyBankRef}
                      maxLength={100}
                      onChange={(e) => setVerifyBankRef(e.target.value)}
                    />
                    <Input
                      label="Bank verified on (optional)"
                      type="date"
                      value={verifyBankDate}
                      onChange={(e) => setVerifyBankDate(e.target.value)}
                    />
                  </div>
                  <Textarea
                    label="Note (optional)"
                    value={verifyNote}
                    maxLength={1000}
                    onChange={(e) => setVerifyNote(e.target.value)}
                    rows={2}
                  />
                </div>
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

      <Modal
        isOpen={!!retryTarget}
        onClose={() => (isRetrying ? undefined : setRetryTarget(null))}
        title="Retry Tally post"
        size="sm"
      >
        {retryTarget && (
          <div className="space-y-space-3">
            {retryError && <ErrorBanner message={retryError} />}
            <p className="text-sm">
              Re-queue the Tally posting of {formatCurrency(retryTarget.amount)} from{' '}
              <strong>{retryTarget.customer_name || 'this outlet'}</strong>? The outlet balance will change only after
              Tally confirms it.
            </p>
            <div className="flex justify-end gap-space-2">
              <Button variant="outline" disabled={isRetrying} onClick={() => setRetryTarget(null)}>
                Cancel
              </Button>
              <Button variant="primary" icon={RefreshCw} isLoading={isRetrying} onClick={() => void handleConfirmRetry()}>
                Confirm retry
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

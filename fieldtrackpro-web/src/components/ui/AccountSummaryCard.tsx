import React, { useState } from 'react';
import { Wallet, AlertTriangle, Clock, Landmark, Receipt, Paperclip } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from './Card';
import { Button } from './Button';
import { StatusBadge } from './StatusBadge';
import { apiClient } from '../../api/client';
import { AccountSummary } from '../../types';

interface AccountSummaryCardProps {
  account: AccountSummary;
  /** Provided only in the employee/visit context - shows the "Collect Payment" action. */
  onCollectPayment?: () => void;
}

const formatCurrency = (value: string): string => {
  const n = Number(value);
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
};

/**
 * Outlet "Account / Collections" panel: outstanding/due/overdue, aging,
 * recent invoice/payment history, and brand-wise totals.
 *
 * Shared between the employee visit workflow (with the Collect Payment
 * action) and the admin customer detail page (read-only) - one component,
 * not two near-duplicate screens.
 */
export const AccountSummaryCard: React.FC<AccountSummaryCardProps> = ({ account, onCollectPayment }) => {
  const [viewingProofId, setViewingProofId] = useState<string | null>(null);

  const viewProof = async (proofId: string) => {
    setViewingProofId(proofId);
    try {
      const objectUrl = await apiClient.getPaymentProofObjectUrl(proofId);
      window.open(objectUrl, '_blank');
      // One-shot view, not a persistent preview - revoke once the new tab
      // has had a moment to load it, matching this app's blob-lifecycle
      // convention of never leaking object URLs (see PaymentReviewPage).
      setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
    } finally {
      setViewingProofId(null);
    }
  };

  const lastVisitLabel = account.most_recent_visit_date
    ? `${new Date(account.most_recent_visit_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}${account.most_recent_visit_employee_name ? ` · ${account.most_recent_visit_employee_name}` : ''}`
    : 'No visits yet';
  const lastPaymentLabel = account.most_recent_payment
    ? `${formatCurrency(account.most_recent_payment.amount)} · ${account.most_recent_payment.payment_date}`
    : 'No payments yet';

  return (
    <Card variant="default" className="space-y-space-4">
      <CardHeader>
        <div>
          <CardTitle>Outlet Account</CardTitle>
          <CardSubtitle>
            {account.outlet_code ? `Outlet Code: ${account.outlet_code}` : 'Outstanding, aging, and collection history'}
          </CardSubtitle>
        </div>
        <StatusBadge status={account.collection_status} />
      </CardHeader>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-space-3">
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <div className="flex items-start gap-space-1.5 text-on-surface-variant font-caption text-xs uppercase tracking-wide mb-1 break-words">
            <Receipt className="w-3.5 h-3.5 shrink-0 mt-0.5" /> <span>Total Billed</span>
          </div>
          <p className="font-headline-sm text-lg font-bold text-primary break-words">{formatCurrency(account.total_invoiced)}</p>
        </div>
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <div className="flex items-start gap-space-1.5 text-on-surface-variant font-caption text-xs uppercase tracking-wide mb-1 break-words">
            <Wallet className="w-3.5 h-3.5 shrink-0 mt-0.5" /> <span>Outstanding</span>
          </div>
          <p className="font-headline-sm text-lg font-bold text-primary break-words">{formatCurrency(account.total_outstanding)}</p>
        </div>
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <div className="flex items-start gap-space-1.5 text-on-surface-variant font-caption text-xs uppercase tracking-wide mb-1 break-words">
            <Landmark className="w-3.5 h-3.5 shrink-0 mt-0.5" /> <span>Paid to Date</span>
          </div>
          <p className="font-headline-sm text-lg font-bold text-primary break-words">{formatCurrency(account.total_paid)}</p>
        </div>
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <div className="flex items-start gap-space-1.5 text-on-surface-variant font-caption text-xs uppercase tracking-wide mb-1 break-words">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> <span>Overdue</span>
          </div>
          <p className={`font-headline-sm text-lg font-bold break-words ${Number(account.overdue_amount) > 0 ? 'text-error' : 'text-primary'}`}>
            {formatCurrency(account.overdue_amount)}
          </p>
        </div>
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <div className="flex items-start gap-space-1.5 text-on-surface-variant font-caption text-xs uppercase tracking-wide mb-1 break-words">
            <Clock className="w-3.5 h-3.5 shrink-0 mt-0.5" /> <span>Days Outstanding</span>
          </div>
          <p className="font-headline-sm text-lg font-bold text-primary break-words">{account.max_days_outstanding}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3 text-sm">
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <p className="font-caption text-xs uppercase tracking-wide text-on-surface-variant mb-0.5 break-words">Last Payment</p>
          <p className="font-medium text-on-surface break-words">{lastPaymentLabel}</p>
        </div>
        <div className="min-w-0 p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
          <p className="font-caption text-xs uppercase tracking-wide text-on-surface-variant mb-0.5 break-words">Last Visit</p>
          <p className="font-medium text-on-surface break-words">{lastVisitLabel}</p>
        </div>
      </div>

      {onCollectPayment && (
        <Button variant="primary" className="w-full" onClick={onCollectPayment}>
          Collect Payment
        </Button>
      )}

      {account.brand_summary.length > 0 && (
        <div>
          <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2">
            Brand History
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-on-surface-variant font-caption text-xs uppercase tracking-wider border-b border-outline-variant">
                  <th className="py-space-1.5 pr-space-2">Brand</th>
                  <th className="py-space-1.5 pr-space-2">Invoiced</th>
                  <th className="py-space-1.5 pr-space-2">Paid</th>
                  <th className="py-space-1.5 pr-space-2">Outstanding</th>
                  <th className="py-space-1.5 pr-space-2">Overdue</th>
                  <th className="py-space-1.5 pr-space-2">Invoices</th>
                  <th className="py-space-1.5">Latest Invoice</th>
                </tr>
              </thead>
              <tbody>
                {account.brand_summary.map((b) => (
                  <tr key={b.brand} className="border-b border-surface-container-highest last:border-0">
                    <td className="py-space-1.5 pr-space-2 font-medium text-on-surface">{b.brand}</td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface">{formatCurrency(b.total_invoiced)}</td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface">{formatCurrency(b.total_paid)}</td>
                    <td className="py-space-1.5 pr-space-2 font-bold text-primary">{formatCurrency(b.total_outstanding)}</td>
                    <td className={`py-space-1.5 pr-space-2 font-medium ${Number(b.overdue_amount) > 0 ? 'text-error' : 'text-on-surface-variant'}`}>
                      {formatCurrency(b.overdue_amount)}
                    </td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface-variant">{b.invoice_count}</td>
                    <td className="py-space-1.5 text-on-surface-variant">{b.latest_invoice_date || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {account.recent_invoices.length > 0 && (
        <div>
          <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2">
            Invoice History
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-on-surface-variant font-caption text-xs uppercase tracking-wider border-b border-outline-variant">
                  <th className="py-space-1.5 pr-space-2">Invoice</th>
                  <th className="py-space-1.5 pr-space-2">Date</th>
                  <th className="py-space-1.5 pr-space-2">Amount</th>
                  <th className="py-space-1.5 pr-space-2">Remaining</th>
                  <th className="py-space-1.5 pr-space-2">Days</th>
                  <th className="py-space-1.5">Status</th>
                </tr>
              </thead>
              <tbody>
                {account.recent_invoices.map((inv) => (
                  <tr key={inv.id} className="border-b border-surface-container-highest last:border-0">
                    <td className="py-space-1.5 pr-space-2 font-medium text-on-surface">{inv.invoice_number}</td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface-variant">{inv.invoice_date}</td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface">{formatCurrency(inv.amount)}</td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface">{formatCurrency(inv.remaining_amount)}</td>
                    <td className="py-space-1.5 pr-space-2 text-on-surface-variant">{inv.days_outstanding}</td>
                    <td className="py-space-1.5">
                      <StatusBadge status={inv.aging_status} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {account.recent_payments.length > 0 && (
        <div>
          <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2">
            Payment History
          </p>
          <div className="space-y-space-1.5">
            {account.recent_payments.map((p) => (
              <div key={p.id} className="flex items-center justify-between text-sm py-space-1.5 border-b border-surface-container-highest last:border-0">
                <div>
                  <span className="font-medium text-on-surface">{formatCurrency(p.amount)}</span>
                  <span className="text-on-surface-variant ml-space-2">
                    {p.payment_method} &middot; {p.payment_date}
                    {p.utr_reference ? ` · UTR ${p.utr_reference}` : ''}
                    {p.cheque_number ? ` · Chq ${p.cheque_number}` : ''}
                  </span>
                </div>
                <div className="flex items-center gap-space-2 shrink-0">
                  {p.proofs.length > 0 && (
                    <Button
                      variant="outline" size="sm" icon={Paperclip}
                      isLoading={viewingProofId === p.proofs[0].id}
                      onClick={() => void viewProof(p.proofs[0].id)}
                    >
                      Proof
                    </Button>
                  )}
                  <StatusBadge status={p.status} size="sm" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {account.recent_invoices.length === 0 && (
        <p className="font-caption text-xs text-on-surface-variant text-center py-space-2">
          No invoices on record for this outlet yet.
        </p>
      )}
    </Card>
  );
};

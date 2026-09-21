import React, { useState } from 'react';
import { Wallet, AlertTriangle, Clock, Landmark, Receipt, Paperclip, Calendar, TrendingUp } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from './Card';
import { Button } from './Button';
import { StatusBadge } from './StatusBadge';
import { PaymentMethodBadge } from './PaymentMethodBadge';
import { apiClient } from '../../api/client';
import { AccountSummary } from '../../types';

interface AccountSummaryCardProps {
  account: AccountSummary;
  /** Provided only in the employee/visit context - shows the "Collect Payment" action. */
  onCollectPayment?: () => void;
}

const formatCurrency = (value: string | number): string => {
  const n = Number(value);
  if (isNaN(n)) return '₹0';
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
};

/**
 * Outlet "Account / Collections" panel: outstanding/due/overdue, aging,
 * recent invoice/payment history, and brand-wise totals.
 */
export const AccountSummaryCard: React.FC<AccountSummaryCardProps> = ({ account, onCollectPayment }) => {
  const [viewingProofId, setViewingProofId] = useState<string | null>(null);

  const viewProof = async (proofId: string) => {
    setViewingProofId(proofId);
    try {
      const objectUrl = await apiClient.getPaymentProofObjectUrl(proofId);
      window.open(objectUrl, '_blank');
      setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
    } finally {
      setViewingProofId(null);
    }
  };

  const lastVisitLabel = account.most_recent_visit_date
    ? `${new Date(account.most_recent_visit_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}${account.most_recent_visit_employee_name ? ` · ${account.most_recent_visit_employee_name}` : ''}`
    : 'No visits yet';

  const lastPaymentLabel = account.most_recent_payment
    ? `${formatCurrency(account.most_recent_payment.amount)} · ${account.most_recent_payment.payment_date}`
    : 'No payments yet';

  const isOverdue = Number(account.overdue_amount) > 0;
  const daysOut = Number(account.max_days_outstanding) || 0;

  return (
    <Card variant="default" className="space-y-6 overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-outline-variant/30">
        <div>
          <CardTitle className="text-xl font-bold tracking-tight">Outlet Account</CardTitle>
          <CardSubtitle className="text-xs text-on-surface-variant/80 mt-0.5">
            {account.outlet_code ? `Outlet Code: ${account.outlet_code}` : 'Outstanding, aging, and collection history'}
          </CardSubtitle>
        </div>
        <StatusBadge status={account.collection_status} />
      </CardHeader>

      {/* Top 5 KPI Cards - Responsive, perfectly spaced, zero clipping or overflow */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* Total Billed */}
        <div className="min-w-0 p-3.5 bg-surface-container-low rounded-xl border border-outline-variant/60 flex flex-col justify-between hover:border-outline-variant transition-colors shadow-sm">
          <div className="flex items-center gap-1.5 text-on-surface-variant mb-2">
            <Receipt className="w-4 h-4 shrink-0 text-primary/70" />
            <span className="text-[11px] font-semibold uppercase tracking-wider truncate">Total Billed</span>
          </div>
          <p className="text-lg font-bold text-primary tracking-tight whitespace-nowrap truncate">
            {formatCurrency(account.total_invoiced)}
          </p>
        </div>

        {/* Outstanding */}
        <div className="min-w-0 p-3.5 bg-surface-container-low rounded-xl border border-outline-variant/60 flex flex-col justify-between hover:border-outline-variant transition-colors shadow-sm">
          <div className="flex items-center gap-1.5 text-on-surface-variant mb-2">
            <Wallet className="w-4 h-4 shrink-0 text-amber-600" />
            <span className="text-[11px] font-semibold uppercase tracking-wider truncate">Outstanding</span>
          </div>
          <p className="text-lg font-bold text-primary tracking-tight whitespace-nowrap truncate">
            {formatCurrency(account.total_outstanding)}
          </p>
        </div>

        {/* Paid to Date */}
        <div className="min-w-0 p-3.5 bg-surface-container-low rounded-xl border border-outline-variant/60 flex flex-col justify-between hover:border-outline-variant transition-colors shadow-sm">
          <div className="flex items-center gap-1.5 text-on-surface-variant mb-2">
            <Landmark className="w-4 h-4 shrink-0 text-emerald-600" />
            <span className="text-[11px] font-semibold uppercase tracking-wider truncate">Paid to Date</span>
          </div>
          <p className="text-lg font-bold text-emerald-700 tracking-tight whitespace-nowrap truncate">
            {formatCurrency(account.total_paid)}
          </p>
        </div>

        {/* Overdue */}
        <div className={`min-w-0 p-3.5 rounded-xl border flex flex-col justify-between transition-colors shadow-sm ${
          isOverdue 
            ? 'bg-rose-50/70 dark:bg-rose-950/20 border-rose-300 dark:border-rose-900/60' 
            : 'bg-surface-container-low border-outline-variant/60'
        }`}>
          <div className="flex items-center gap-1.5 text-on-surface-variant mb-2">
            <AlertTriangle className={`w-4 h-4 shrink-0 ${isOverdue ? 'text-rose-600' : 'text-primary/70'}`} />
            <span className={`text-[11px] font-semibold uppercase tracking-wider truncate ${isOverdue ? 'text-rose-700 font-bold' : ''}`}>
              Overdue
            </span>
          </div>
          <p className={`text-lg font-bold tracking-tight whitespace-nowrap truncate ${isOverdue ? 'text-rose-600' : 'text-primary'}`}>
            {formatCurrency(account.overdue_amount)}
          </p>
        </div>

        {/* Days Outstanding */}
        <div className="min-w-0 p-3.5 bg-surface-container-low rounded-xl border border-outline-variant/60 flex flex-col justify-between hover:border-outline-variant transition-colors shadow-sm col-span-2 sm:col-span-1">
          <div className="flex items-center gap-1.5 text-on-surface-variant mb-2">
            <Clock className={`w-4 h-4 shrink-0 ${daysOut > 30 ? 'text-amber-600' : 'text-primary/70'}`} />
            <span className="text-[11px] font-semibold uppercase tracking-wider truncate">Days Due</span>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-lg font-bold text-primary tracking-tight">{account.max_days_outstanding}</span>
            <span className="text-xs text-on-surface-variant/70 font-medium">days</span>
          </div>
        </div>
      </div>

      {/* Activity Timeline Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <div className="p-3.5 bg-surface-container-low/70 rounded-xl border border-outline-variant/40 flex items-start gap-3">
          <div className="p-2 rounded-lg bg-surface-container-high shrink-0 text-primary/80">
            <Wallet className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant/70 mb-0.5">Last Payment</p>
            <p className="font-semibold text-on-surface truncate">{lastPaymentLabel}</p>
          </div>
        </div>

        <div className="p-3.5 bg-surface-container-low/70 rounded-xl border border-outline-variant/40 flex items-start gap-3">
          <div className="p-2 rounded-lg bg-surface-container-high shrink-0 text-primary/80">
            <Calendar className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant/70 mb-0.5">Last Visit</p>
            <p className="font-semibold text-on-surface truncate">{lastVisitLabel}</p>
          </div>
        </div>
      </div>

      {onCollectPayment && (
        <Button variant="primary" className="w-full py-2.5 font-semibold tracking-wide shadow-sm" onClick={onCollectPayment}>
          Collect Payment
        </Button>
      )}

      {/* Brand History Table - Structured & Right-aligned amounts */}
      {account.brand_summary.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-primary" /> Brand History
            </p>
            <span className="text-xs text-on-surface-variant/70">{account.brand_summary.length} brand{account.brand_summary.length > 1 ? 's' : ''}</span>
          </div>
          <div className="overflow-x-auto rounded-xl border border-outline-variant/50 shadow-sm">
            <table className="w-full text-xs sm:text-sm">
              <thead>
                <tr className="bg-surface-container-high/60 text-on-surface-variant font-semibold uppercase text-[11px] tracking-wider border-b border-outline-variant/40">
                  <th className="py-2.5 px-3 text-left">Brand</th>
                  <th className="py-2.5 px-3 text-right">Invoiced</th>
                  <th className="py-2.5 px-3 text-right">Paid</th>
                  <th className="py-2.5 px-3 text-right">Outstanding</th>
                  <th className="py-2.5 px-3 text-right">Overdue</th>
                  <th className="py-2.5 px-3 text-center">Invoices</th>
                  <th className="py-2.5 px-3 text-right">Latest Invoice</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20 bg-surface">
                {account.brand_summary.map((b) => {
                  const brandOverdue = Number(b.overdue_amount) > 0;
                  return (
                    <tr key={b.brand} className="hover:bg-surface-container-low/40 transition-colors">
                      <td className="py-2.5 px-3 font-semibold text-on-surface">{b.brand}</td>
                      <td className="py-2.5 px-3 text-right text-on-surface-variant whitespace-nowrap">{formatCurrency(b.total_invoiced)}</td>
                      <td className="py-2.5 px-3 text-right text-emerald-700 font-medium whitespace-nowrap">{formatCurrency(b.total_paid)}</td>
                      <td className="py-2.5 px-3 text-right font-bold text-primary whitespace-nowrap">{formatCurrency(b.total_outstanding)}</td>
                      <td className={`py-2.5 px-3 text-right font-semibold whitespace-nowrap ${brandOverdue ? 'text-rose-600' : 'text-on-surface-variant/70'}`}>
                        {formatCurrency(b.overdue_amount)}
                      </td>
                      <td className="py-2.5 px-3 text-center text-on-surface-variant">{b.invoice_count}</td>
                      <td className="py-2.5 px-3 text-right text-on-surface-variant/80 whitespace-nowrap">{b.latest_invoice_date || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Outstanding Ageing Breakdown */}
      {account.aging_buckets && Object.keys(account.aging_buckets).length > 0 && (
        <div className="space-y-2.5">
          <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold">
            Outstanding Ageing
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            {[
              { key: '0-30', label: '0–30 Days', borderClass: 'border-outline-variant/60', textClass: 'text-primary' },
              { key: '31-60', label: '31–60 Days', borderClass: 'border-amber-300 dark:border-amber-900/60', textClass: 'text-amber-700 dark:text-amber-400 font-bold' },
              { key: '61-90', label: '61–90 Days', borderClass: 'border-orange-300 dark:border-orange-900/60', textClass: 'text-orange-700 dark:text-orange-400 font-bold' },
              { key: '90+', label: '90+ Days', borderClass: 'border-rose-300 dark:border-rose-900/60', textClass: 'text-rose-600 font-bold' },
            ].map(({ key, label, borderClass, textClass }) => {
              const val = account.aging_buckets?.[key] || '0';
              const numVal = Number(val);
              const hasAmount = numVal > 0;
              return (
                <div 
                  key={key} 
                  className={`p-3 rounded-xl border transition-all ${
                    hasAmount 
                      ? `${borderClass} bg-surface-container shadow-xs` 
                      : 'border-outline-variant/40 bg-surface-container-low/40 opacity-70'
                  }`}
                >
                  <span className="text-[11px] font-medium text-on-surface-variant uppercase tracking-wider block mb-1">
                    {label}
                  </span>
                  <span className={`text-base tracking-tight block truncate ${hasAmount ? textClass : 'text-on-surface-variant/60'}`}>
                    {formatCurrency(val)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Invoice History Table */}
      {account.recent_invoices.length > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold">
              Invoice History
            </p>
            <span className="text-xs text-on-surface-variant/70">{account.recent_invoices.length} invoice{account.recent_invoices.length > 1 ? 's' : ''}</span>
          </div>
          <div className="overflow-x-auto rounded-xl border border-outline-variant/50 shadow-sm">
            <table className="w-full text-xs sm:text-sm">
              <thead>
                <tr className="bg-surface-container-high/60 text-on-surface-variant font-semibold uppercase text-[11px] tracking-wider border-b border-outline-variant/40">
                  <th className="py-2.5 px-3 text-left">Invoice</th>
                  <th className="py-2.5 px-3 text-left">Date</th>
                  <th className="py-2.5 px-3 text-right">Amount</th>
                  <th className="py-2.5 px-3 text-right">Remaining</th>
                  <th className="py-2.5 px-3 text-center">Days</th>
                  <th className="py-2.5 px-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20 bg-surface">
                {account.recent_invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-surface-container-low/40 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-on-surface font-mono">{inv.invoice_number}</td>
                    <td className="py-2.5 px-3 text-on-surface-variant whitespace-nowrap">{inv.invoice_date}</td>
                    <td className="py-2.5 px-3 text-right font-medium text-on-surface whitespace-nowrap">{formatCurrency(inv.amount)}</td>
                    <td className="py-2.5 px-3 text-right font-bold text-primary whitespace-nowrap">{formatCurrency(inv.remaining_amount)}</td>
                    <td className="py-2.5 px-3 text-center text-on-surface-variant">{inv.days_outstanding}</td>
                    <td className="py-2.5 px-3 text-center whitespace-nowrap">
                      <StatusBadge status={inv.aging_status} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Payment History */}
      {account.recent_payments.length > 0 && (
        <div className="space-y-2.5">
          <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold">
            Payment History
          </p>
          <div className="space-y-2">
            {account.recent_payments.map((p) => (
              <div key={p.id} className="p-3 bg-surface-container-low rounded-xl border border-outline-variant/50 flex flex-col gap-2">
                <div className="flex items-center justify-between text-sm flex-wrap gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-emerald-700 text-base">{formatCurrency(p.amount)}</span>
                    <PaymentMethodBadge method={p.payment_method} chequeNumber={p.cheque_number} size="sm" />
                    <span className="text-on-surface-variant text-xs">
                      {p.payment_date}
                      {p.utr_reference ? ` · UTR ${p.utr_reference}` : ''}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
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

                {p.allocations && p.allocations.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1 border-t border-outline-variant/20">
                    {p.allocations.map((a) => (
                      <span
                        key={a.brand}
                        className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-primary/10 text-primary"
                      >
                        {a.brand}: {formatCurrency(a.allocated_amount)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {account.recent_invoices.length === 0 && (
        <p className="text-xs text-on-surface-variant/70 text-center py-3 italic">
          No invoices on record for this outlet yet.
        </p>
      )}
    </Card>
  );
};

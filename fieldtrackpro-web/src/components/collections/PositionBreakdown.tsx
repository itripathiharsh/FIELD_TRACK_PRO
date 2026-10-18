import React from 'react';
import { AlertTriangle, Info, Hourglass } from 'lucide-react';
import { AgeingBreakdown, PositionFields } from '../../types';

import { formatMoney, hasPosition, RECONCILE_WARNING } from './positionFormat';

const InfoTip: React.FC<{ text: string }> = ({ text }) => (
  <span title={text} aria-label={text} role="img" className="inline-flex align-middle ml-1 text-on-surface-variant/70 cursor-help">
    <Info className="w-3 h-3" aria-hidden="true" />
  </span>
);

export const ReconcileWarning: React.FC<{ reconciles?: boolean; className?: string }> = ({ reconciles, className = '' }) => {
  if (reconciles !== false) return null;
  return (
    <span
      role="alert"
      data-testid="reconcile-warning"
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold bg-error-container text-on-error-container border-error ${className}`}
    >
      <AlertTriangle className="w-3 h-3 shrink-0" aria-hidden="true" />
      {RECONCILE_WARNING}
    </span>
  );
};

export interface PositionData extends PositionFields {
  total_invoiced: string;
  total_outstanding: string;
  verified_awaiting_tally_amount?: string;
}

const TERMS = {
  opening: 'Balance carried forward from Tally before the app started tracking invoices (the baseline).',
  invoiced: 'Total billed to this account: Tally baseline sales plus invoices created in the app.',
  paid: 'Money already received AND posted to Tally (Tally collection plus payments confirmed in Tally). Verified payments not yet in Tally are not included.',
  outstanding: 'What the customer still owes right now. Equals Opening + Invoiced − Paid in Tally.',
};

const Term: React.FC<{ label: string; value: string | undefined; tip: string; strong?: boolean; testId: string }> = ({ label, value, tip, strong, testId }) => (
  <div className="min-w-0 text-center">
    <p className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold">
      {label}<InfoTip text={tip} />
    </p>
    <p data-testid={testId} className={`text-base tracking-tight whitespace-nowrap ${strong ? 'font-bold text-primary' : 'font-semibold text-on-surface'}`}>
      {formatMoney(value)}
    </p>
  </div>
);

const Op: React.FC<{ c: string }> = ({ c }) => (
  <span aria-hidden="true" className="text-lg font-bold text-on-surface-variant self-end pb-0.5">{c}</span>
);

interface PositionBreakdownProps {
  position: PositionData;
  className?: string;
}

/** Visible reconciliation: Opening (Tally) + Invoiced − Paid in Tally = Outstanding. */
export const PositionBreakdown: React.FC<PositionBreakdownProps> = ({ position, className = '' }) => {
  if (!hasPosition(position)) return null;
  const awaiting = Number(position.verified_awaiting_tally_amount);
  const advance = Number(position.advance_credit);

  return (
    <div data-testid="position-breakdown" className={`p-3.5 rounded-xl border border-outline-variant/60 bg-surface-container-low space-y-2 ${className}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold">How the outstanding is calculated</p>
        <ReconcileWarning reconciles={position.reconciles} />
      </div>
      <div
        className="flex flex-wrap items-end justify-center gap-x-3 gap-y-2"
        aria-label="Opening balance plus Invoiced minus Paid in Tally equals Outstanding"
      >
        <Term label="Opening balance (Tally)" value={position.opening_balance} tip={TERMS.opening} testId="pos-opening" />
        <Op c="+" />
        <Term label="Invoiced" value={position.total_invoiced} tip={TERMS.invoiced} testId="pos-invoiced" />
        <Op c="−" />
        <Term label="Paid in Tally" value={position.paid_in_tally} tip={TERMS.paid} testId="pos-paid" />
        <Op c="=" />
        <Term label="Outstanding" value={position.total_outstanding} tip={TERMS.outstanding} strong testId="pos-outstanding" />
      </div>
      {awaiting > 0 && (
        <p data-testid="pos-awaiting" className="flex items-center justify-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-400">
          <Hourglass className="w-3 h-3 shrink-0" aria-hidden="true" />
          Verified, awaiting Tally {formatMoney(position.verified_awaiting_tally_amount)} (not yet deducted)
        </p>
      )}
      {advance > 0 && (
        <p data-testid="pos-advance" className="text-center text-xs text-emerald-700 font-semibold">
          Advance credit (paid beyond what is owed): {formatMoney(position.advance_credit)} — included in the opening balance, never shown as negative outstanding.
        </p>
      )}
    </div>
  );
};

const AGEING_ROWS: { key: keyof AgeingBreakdown; label: string; hint: string; bar: string; text: string }[] = [
  { key: 'normal', label: 'Normal (<21 days)', hint: 'Invoices less than 21 days old.', bar: 'bg-emerald-500', text: 'text-primary' },
  { key: 'warning', label: 'Warning (21–25 days)', hint: 'Invoices 21 to 25 days old — collect soon.', bar: 'bg-amber-400', text: 'text-amber-600' },
  { key: 'overdue', label: 'Overdue (26+ days)', hint: 'Invoices 26 or more days old.', bar: 'bg-rose-500', text: 'text-rose-600' },
  { key: 'baseline_current', label: 'Carried-forward balance, current', hint: 'Old Tally balance (before the app) that is less than 30 days old or has no age on record.', bar: 'bg-slate-400', text: 'text-on-surface' },
  { key: 'baseline_overdue', label: 'Carried-forward balance, overdue (30+ days)', hint: 'Old Tally balance (before the app) that is 30 or more days old; counts as overdue.', bar: 'bg-rose-800', text: 'text-rose-700' },
];

interface AgeingTableProps {
  ageing: AgeingBreakdown | undefined;
  /** Backend total_outstanding - shown in the total row. */
  totalOutstanding: string;
  className?: string;
}

/** Ageing split from the backend `ageing` object only; the rows add up to Outstanding. */
export const AgeingTable: React.FC<AgeingTableProps> = ({ ageing, totalOutstanding, className = '' }) => {
  if (!ageing) return null;
  const total = Number(totalOutstanding);
  const sum = AGEING_ROWS.reduce((acc, r) => acc + Number(ageing[r.key] || 0), 0); // visual check only
  const mismatch = Math.abs(sum - total) > 0.005;
  return (
    <div data-testid="ageing-table" className={`space-y-2 ${className}`}>
      <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold">Outstanding by age</p>
      {total > 0 && (
        <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-container-high" aria-hidden="true">
          {AGEING_ROWS.map((r) => {
            const v = Number(ageing[r.key] || 0);
            return v > 0 ? <div key={r.key} className={r.bar} style={{ width: `${(v / total) * 100}%` }} /> : null;
          })}
        </div>
      )}
      <table className="w-full text-xs sm:text-sm">
        <tbody className="divide-y divide-outline-variant/20">
          {AGEING_ROWS.map((r) => (
            <tr key={r.key} data-testid={`ageing-${r.key}`}>
              <td className="py-1.5 pr-2 text-on-surface-variant">
                <span className={`inline-block w-2.5 h-2.5 rounded-sm mr-2 align-middle ${r.bar}`} aria-hidden="true" />
                {r.label}<InfoTip text={r.hint} />
              </td>
              <td className={`py-1.5 text-right whitespace-nowrap font-semibold ${Number(ageing[r.key]) > 0 ? r.text : 'text-on-surface-variant/60'}`}>
                {formatMoney(ageing[r.key])}
              </td>
            </tr>
          ))}
          <tr data-testid="ageing-total" className="border-t border-outline-variant">
            <td className="py-1.5 pr-2 font-bold text-on-surface">Total outstanding</td>
            <td className="py-1.5 text-right whitespace-nowrap font-bold text-primary">{formatMoney(totalOutstanding)}</td>
          </tr>
        </tbody>
      </table>
      {mismatch && (
        <p role="alert" className="text-[11px] font-semibold text-rose-600">
          Age buckets add up to {formatMoney(sum)}, which differs from Outstanding. {RECONCILE_WARNING}.
        </p>
      )}
    </div>
  );
};

import React from 'react';
import { Hourglass } from 'lucide-react';
import { formatMoney as formatCurrency } from '../../utils/money';

export const AWAITING_TALLY_TOOLTIP = 'Verified by admin, will reduce outstanding once posted to Tally';

interface AwaitingTallyAmountProps {
  /** Backend `verified_awaiting_tally_amount`; rendered only when > 0 (never recomputed here). */
  amount: string | number | null | undefined;
  className?: string;
}

/** Small "Verified, awaiting Tally: ₹X" line shown next to Paid/Outstanding when there is something awaiting. */
export const AwaitingTallyAmount: React.FC<AwaitingTallyAmountProps> = ({ amount, className = '' }) => {
  if (!(Number(amount) > 0)) return null;
  return (
    <span
      data-testid="awaiting-tally-amount"
      title={AWAITING_TALLY_TOOLTIP}
      className={`inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700 dark:text-amber-400 ${className}`}
    >
      <Hourglass className="w-3 h-3 shrink-0" aria-hidden="true" />
      Verified, awaiting Tally: {formatCurrency(amount as string | number)}
    </span>
  );
};

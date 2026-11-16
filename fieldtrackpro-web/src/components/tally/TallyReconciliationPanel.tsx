import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '../../api/client';
import { TallyReconciliation } from '../../types';
import { formatMoney } from '../../utils/money';

/**
 * FieldTrack vs Tally, per debtor: Tally opening + invoices + adjustments - receipts
 * - Tally closing must be 0.00. Differences are listed, never hidden.
 */
export const TallyReconciliationPanel: React.FC = () => {
  const [data, setData] = useState<TallyReconciliation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await apiClient.getTallyReconciliation(50));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the reconciliation');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const ok = data && data.debtors_with_difference === 0;
  return (
    <div className="space-y-3 rounded-xl border border-outline-variant/60 bg-surface-container-low p-4" data-testid="tally-reconciliation">
      <div className="flex items-center justify-between gap-2">
        <h5 className="text-sm font-bold text-primary flex items-center gap-2">
          {ok ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <AlertTriangle className="w-4 h-4 text-amber-600" />}
          FieldTrack vs Tally reconciliation
        </h5>
        <button type="button" onClick={() => void load()} className="text-xs text-on-surface-variant flex items-center gap-1" disabled={loading}>
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>
      {error && <p className="text-xs text-rose-700">{error}</p>}
      {data && (
        <>
          <p className="text-xs text-on-surface-variant">
            {data.debtors_reconciled.toLocaleString('en-IN')} of {data.counts.debtors.toLocaleString('en-IN')} debtors agree with
            their Tally ledger balance to the paisa.
            {data.debtors_with_difference > 0 && ` ${data.debtors_with_difference} differ (listed below).`}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {([
              ['Opening (Tally)', data.totals.opening],
              ['Invoices', data.totals.invoiced],
              ['Adjustments', data.totals.adjustments],
              ['Receipts', data.totals.received],
              ['Closing (Tally)', data.totals.closing],
              ['Open bills (Tally)', data.totals.open_bills],
              ['Unallocated', data.unallocated_total],
              ['Difference', data.totals.difference],
            ] as const).map(([label, value]) => (
              <div key={label} className="rounded-lg border border-outline-variant/40 p-2">
                <div className="text-on-surface-variant">{label}</div>
                <div className="font-semibold text-primary">{formatMoney(value)}</div>
              </div>
            ))}
          </div>
          {data.retired.length > 0 && (
            <p className="text-xs text-on-surface-variant">
              Kept for history, no longer counted (changed, cancelled or deleted in Tally):{' '}
              {data.retired.map((r) => `${r.count} ${r.kind}${r.count === 1 ? '' : 's'} (${(r.reason || '').toLowerCase().replace(/_/g, ' ')})`).join(', ')}.
            </p>
          )}
          {data.field_collections_linked_to_retired_receipt > 0 && (
            <p className="text-xs text-amber-700">
              {data.field_collections_linked_to_retired_receipt} field collection(s) are linked to a receipt Tally no longer has; re-link them.
            </p>
          )}
          {data.differences.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-on-surface-variant">
                    <th className="py-1 pr-2">Outlet</th>
                    <th className="py-1 pr-2 text-right">Opening</th>
                    <th className="py-1 pr-2 text-right">Invoiced</th>
                    <th className="py-1 pr-2 text-right">Adjusted</th>
                    <th className="py-1 pr-2 text-right">Received</th>
                    <th className="py-1 pr-2 text-right">Tally closing</th>
                    <th className="py-1 text-right">Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {data.differences.map((d) => (
                    <tr key={d.customer_id} className="border-t border-outline-variant/30">
                      <td className="py-1 pr-2">{d.name}{d.outlet_code ? ` (${d.outlet_code})` : ''}</td>
                      <td className="py-1 pr-2 text-right">{formatMoney(d.opening)}</td>
                      <td className="py-1 pr-2 text-right">{formatMoney(d.invoiced)}</td>
                      <td className="py-1 pr-2 text-right">{formatMoney(d.adjustments)}</td>
                      <td className="py-1 pr-2 text-right">{formatMoney(d.received)}</td>
                      <td className="py-1 pr-2 text-right">{formatMoney(d.closing)}</td>
                      <td className="py-1 text-right font-semibold text-rose-700">{formatMoney(d.difference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};

import React, { useCallback, useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { apiClient } from '../../api/client';
import type { AccountHistoryItem } from '../../types';
import { formatMoney } from '../../utils/money';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../ui/Card';
import { Button } from '../ui/Button';

const PAGE = 50;
const KIND_LABEL: Record<AccountHistoryItem['kind'], string> = {
  INVOICE: 'Invoice',
  PAYMENT: 'Receipt',
  ADJUSTMENT: 'Adjustment',
};

/** 2.1.0: full account history of a physical outlet across all its linked Tally ledgers. */
export const AccountHistoryTable: React.FC<{ customerId: string }> = ({ customerId }) => {
  const [items, setItems] = useState<AccountHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (off: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.getCustomerHistory(customerId, { limit: PAGE, offset: off });
      setItems(Array.isArray(res?.items) ? res.items : []);
      setTotal(Number(res?.total) || 0);
      setOffset(off);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the account history');
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    void load(0);
  }, [load]);

  return (
    <Card data-testid="account-history">
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2">
            <History className="w-5 h-5 text-primary" /> Account history
          </CardTitle>
          <CardSubtitle>Every bill, receipt and adjustment of all Tally ledgers linked to this shop, newest first</CardSubtitle>
        </div>
      </CardHeader>
      {error && <p className="text-sm text-rose-700 px-4 pb-3">{error}</p>}
      {!error && !loading && items.length === 0 && (
        <p className="text-xs text-on-surface-variant/70 text-center py-3 italic">No account history yet.</p>
      )}
      {items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-surface-container-low text-on-surface-variant">
              <tr>
                <th className="text-left px-3 py-2">Date</th>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Voucher</th>
                <th className="text-right px-3 py-2">Amount</th>
                <th className="text-left px-3 py-2">Brand</th>
                <th className="text-left px-3 py-2">Tally ledger</th>
                <th className="text-left px-3 py-2">Bill</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr
                  key={`${it.date}-${it.voucher_number}-${i}`}
                  data-testid="history-row"
                  className={`border-t border-outline-variant/40 ${it.retired ? 'opacity-60 line-through' : ''}`}
                  title={it.retired ? `Retired: ${it.retired_reason ?? 'no longer in Tally'}` : it.narration ?? undefined}
                >
                  <td className="px-3 py-2 whitespace-nowrap">{it.date}</td>
                  <td className="px-3 py-2">
                    {KIND_LABEL[it.kind]}
                    {it.retired && (
                      <span className="ml-1 no-underline text-[10px] font-bold text-rose-700" data-testid="retired-marker">
                        RETIRED
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">{[it.voucher_type, it.voucher_number].filter(Boolean).join(' ')}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap font-semibold">{formatMoney(it.amount)}</td>
                  <td className="px-3 py-2">{it.brand ?? '—'}</td>
                  <td className="px-3 py-2">{it.ledger_name ?? '—'}</td>
                  <td className="px-3 py-2 font-mono">{it.bill_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > PAGE && (
        <div className="flex items-center justify-between px-4 py-3 text-xs text-on-surface-variant">
          <span data-testid="history-range">
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={loading || offset === 0} onClick={() => load(Math.max(offset - PAGE, 0))}>
              Newer
            </Button>
            <Button variant="secondary" disabled={loading || offset + PAGE >= total} onClick={() => load(offset + PAGE)}>
              Older
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
};

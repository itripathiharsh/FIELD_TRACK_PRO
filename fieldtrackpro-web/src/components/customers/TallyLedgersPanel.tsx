import React from 'react';
import { CheckCircle2, AlertTriangle, Star, BookOpen } from 'lucide-react';
import type { LedgerPosition, LedgerRead } from '../../types';
import { formatMoney } from '../../utils/money';

interface Props {
  /** Per-ledger positions from `/customers/{id}/account` (outlet totals = sum of these). */
  positions?: LedgerPosition[];
  /** Ledger master rows from `/customers/{id}` (primary marker, brand source). Optional. */
  ledgers?: LedgerRead[];
}

/**
 * 2.1.0: the Tally debtor ledgers linked to this physical shop. Each ledger keeps its own Tally
 * identity, balance and reconciliation; the outlet figures above are the sum of these rows.
 */
export const TallyLedgersPanel: React.FC<Props> = ({ positions, ledgers }) => {
  const rows = positions ?? [];
  if (rows.length === 0) return null;
  const byId = new Map((ledgers ?? []).map((l) => [l.id, l]));
  return (
    <div data-testid="tally-ledgers" className="space-y-2.5">
      <p className="text-xs uppercase tracking-wider text-on-surface-variant font-bold flex items-center gap-1.5">
        <BookOpen className="w-3.5 h-3.5 text-primary" /> Tally ledgers
        <span className="normal-case font-medium text-on-surface-variant/70">
          ({rows.length} ledger{rows.length > 1 ? 's' : ''} linked to this shop)
        </span>
      </p>
      <div className="overflow-x-auto rounded-xl border border-outline-variant/60">
        <table className="w-full text-xs">
          <thead className="bg-surface-container-low text-on-surface-variant">
            <tr>
              <th className="text-left px-3 py-2 font-semibold">Ledger</th>
              <th className="text-left px-3 py-2 font-semibold">Brand</th>
              <th className="text-right px-3 py-2 font-semibold">Opening</th>
              <th className="text-right px-3 py-2 font-semibold">Closing (Tally)</th>
              <th className="text-right px-3 py-2 font-semibold">Outstanding</th>
              <th className="text-center px-3 py-2 font-semibold">Reconciles</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const meta = byId.get(p.ledger_id);
              const diff = Number(p.tally_difference ?? 0);
              return (
                <tr key={p.ledger_id} data-testid="tally-ledger-row" className="border-t border-outline-variant/40">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      {meta?.is_primary && (
                        <span title="Primary ledger (outlet name and contact come from it)" data-testid="primary-ledger">
                          <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-400" aria-label="Primary ledger" />
                        </span>
                      )}
                      <span className="font-semibold text-on-surface">{p.name}</span>
                    </div>
                    {p.tally_outlet_code && <span className="font-mono text-[10px] text-on-surface-variant">{p.tally_outlet_code}</span>}
                  </td>
                  <td className="px-3 py-2">
                    {p.brand ?? <span className="italic text-on-surface-variant/70">Unbranded</span>}
                    {meta?.brand_source === 'OVERRIDE' && (
                      <span className="ml-1 text-[10px] text-on-surface-variant" title="Brand supplied by the client/admin (Tally gives none)">
                        (set manually)
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">{formatMoney(p.opening_balance ?? 0)}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">{formatMoney(p.closing_balance ?? 0)}</td>
                  <td className="px-3 py-2 text-right whitespace-nowrap font-semibold">{formatMoney(p.outstanding)}</td>
                  <td className="px-3 py-2 text-center">
                    {p.reconciles && diff === 0 ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 inline" aria-label="Reconciles with Tally" />
                    ) : (
                      <span className="inline-flex items-center gap-1 text-amber-700 font-semibold" data-testid="ledger-difference">
                        <AlertTriangle className="w-3.5 h-3.5" /> {formatMoney(p.tally_difference ?? 0)}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

import React from 'react';
import { Filter } from 'lucide-react';
import { AppliedFilterItem } from '../../utils/reportFilters';

export interface AppliedFiltersStripProps {
  items: AppliedFilterItem[];
  /** Plain-language rules for what the figures mean (period semantics, "as of" dates...). */
  notes?: string[];
}

/**
 * "Applied filters" summary derived from the exact params sent to the API for the
 * current tab - so the strip can never claim a filter that was not actually applied.
 */
export const AppliedFiltersStrip: React.FC<AppliedFiltersStripProps> = ({ items, notes = [] }) => (
  <div data-testid="applied-filters" className="space-y-1.5 pt-1">
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="inline-flex items-center gap-1 font-label-md text-[11px] uppercase tracking-wider font-semibold text-on-surface-variant">
        <Filter className="w-3 h-3" /> Applied filters:
      </span>
      {items.length === 0 ? (
        <span className="text-xs text-on-surface-variant">None - showing all data</span>
      ) : (
        items.map((it, i) => (
          <span
            key={`${it.label}-${i}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-primary-container bg-primary-tint/20 text-xs text-primary"
          >
            <span className="font-semibold">{it.label}:</span> {it.value}
          </span>
        ))
      )}
    </div>
    {notes.map((n) => (
      <p key={n} className="text-[11px] text-on-surface-variant leading-snug">
        {n}
      </p>
    ))}
  </div>
);

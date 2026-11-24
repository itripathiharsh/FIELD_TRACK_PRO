import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';

export interface MultiSelectOption {
  value: string;
  label: string;
  /** Optional group heading (e.g. "History (read-only) · FY 2025-26"). */
  group?: string;
  hint?: string;
}

interface MultiSelectFilterProps {
  label: string;
  /** Text when nothing is selected (= no filter, everything). */
  allLabel: string;
  options: MultiSelectOption[];
  /** Selected values; [] = all. */
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  disabledReason?: string;
  /** Show the selected values as removable chips under the control (default true). */
  showChips?: boolean;
  testId?: string;
}

/**
 * Multi-select dropdown for the BI filters (Brand, Period / Month, FOS).
 * Nothing selected = no filter. Several values OR together; different filters AND together.
 * Keyboard: Enter/Space opens, Escape closes, Tab moves through the checkboxes.
 */
export const MultiSelectFilter: React.FC<MultiSelectFilterProps> = ({
  label,
  allLabel,
  options,
  value,
  onChange,
  disabled,
  disabledReason,
  showChips = true,
  testId,
}) => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const buttonId = useId();
  const selected = useMemo(() => new Set(value), [value]);
  const labelOf = (v: string) => options.find((o) => o.value === v)?.label ?? v;

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  }, [options, query]);

  const toggle = (v: string) => {
    onChange(selected.has(v) ? value.filter((x) => x !== v) : [...value, v]);
  };
  const allSelected = options.length > 0 && options.every((o) => selected.has(o.value));

  const summary =
    value.length === 0 ? allLabel : value.length === 1 ? labelOf(value[0]) : `${value.length} selected`;

  let lastGroup: string | undefined;

  return (
    <div ref={rootRef} className="relative" data-testid={testId}>
      <label htmlFor={buttonId} className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-1">
        {label}
      </label>
      <button
        id={buttonId}
        type="button"
        disabled={disabled}
        title={disabled ? disabledReason : undefined}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={`${label}: ${summary}`}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false);
        }}
        className={`w-full h-9 flex items-center justify-between gap-2 bg-surface border rounded-lg px-2.5 py-1.5 text-xs text-left font-body-md transition-all focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 disabled:opacity-50 disabled:cursor-not-allowed ${
          value.length > 0 ? 'border-primary text-primary font-semibold' : 'border-outline-variant text-on-surface'
        }`}
      >
        <span className="truncate">{summary}</span>
        <ChevronDown className="w-3.5 h-3.5 shrink-0 text-on-surface-variant" />
      </button>

      {open && (
        <div
          className="absolute z-30 mt-1 w-full min-w-[240px] bg-surface border border-outline-variant rounded-lg shadow-lg p-2 space-y-2"
          onKeyDown={(e) => {
            if (e.key === 'Escape') setOpen(false);
          }}
        >
          {options.length > 8 && (
            <input
              type="search"
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${label.toLowerCase()}...`}
              aria-label={`Search ${label}`}
              className="w-full text-xs p-1.5 rounded border border-outline-variant bg-surface text-on-surface"
            />
          )}
          <div className="flex items-center justify-between text-[11px] font-semibold">
            <button
              type="button"
              className="text-primary hover:underline cursor-pointer disabled:opacity-40"
              disabled={allSelected}
              onClick={() => onChange(options.map((o) => o.value))}
            >
              Select all
            </button>
            <button
              type="button"
              className="text-on-surface-variant hover:text-primary hover:underline cursor-pointer disabled:opacity-40"
              disabled={value.length === 0}
              onClick={() => onChange([])}
            >
              Clear all
            </button>
          </div>
          <ul id={listId} role="listbox" aria-multiselectable="true" aria-label={label} className="max-h-64 overflow-y-auto space-y-0.5">
            {shown.length === 0 && <li className="text-xs text-on-surface-variant px-1 py-2">No match.</li>}
            {shown.map((o) => {
              const header = o.group && o.group !== lastGroup ? o.group : null;
              lastGroup = o.group;
              const isOn = selected.has(o.value);
              return (
                <React.Fragment key={o.value}>
                  {header && (
                    <li role="presentation" className="pt-1.5 pb-0.5 px-1 text-[10px] uppercase tracking-wider font-bold text-on-surface-variant">
                      {header}
                    </li>
                  )}
                  <li role="option" aria-selected={isOn}>
                    <label className="flex items-center gap-2 px-1.5 py-1 rounded hover:bg-surface-container cursor-pointer text-xs text-on-surface">
                      <input
                        type="checkbox"
                        value={o.value}
                        checked={isOn}
                        onChange={() => toggle(o.value)}
                        aria-label={o.label}
                        className="accent-current text-primary"
                      />
                      <span className="flex-1 truncate">{o.label}</span>
                      {o.hint && <span className="text-[10px] text-on-surface-variant">{o.hint}</span>}
                      {isOn && <Check className="w-3 h-3 text-primary" />}
                    </label>
                  </li>
                </React.Fragment>
              );
            })}
          </ul>
        </div>
      )}

      {showChips && value.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5" aria-label={`Selected ${label}`}>
          {value.map((v) => (
            <span
              key={v}
              className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-primary-container text-on-primary-container text-[10px] font-semibold max-w-full"
            >
              <span className="truncate">{labelOf(v)}</span>
              <button
                type="button"
                aria-label={`Remove ${labelOf(v)}`}
                onClick={() => onChange(value.filter((x) => x !== v))}
                className="rounded-full hover:bg-on-primary-container/10 p-0.5 cursor-pointer"
              >
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

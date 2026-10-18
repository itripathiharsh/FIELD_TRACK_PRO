/**
 * Single source of truth for the outstanding-ageing display rule.
 * Mirrors backend aging_service.py (WARNING_THRESHOLD_DAYS=21, OVERDUE_THRESHOLD_DAYS=26),
 * which computes age from invoice_date.
 *
 *   days <= 20      -> NORMAL
 *   days 21 .. 25   -> WARNING (yellow)
 *   days >= 26      -> OVERDUE (red, i.e. "after day 25")
 */
export type AgeingLevel = 'NORMAL' | 'WARNING' | 'OVERDUE';

export const AGEING_WARNING_FROM_DAYS = 21;
export const AGEING_OVERDUE_FROM_DAYS = 26;

export function getAgeingLevel(days: number | string | null | undefined): AgeingLevel {
  const d = Number(days);
  if (!Number.isFinite(d)) return 'NORMAL';
  if (d >= AGEING_OVERDUE_FROM_DAYS) return 'OVERDUE';
  if (d >= AGEING_WARNING_FROM_DAYS) return 'WARNING';
  return 'NORMAL';
}

const TEXT_CLASS: Record<AgeingLevel, string> = {
  NORMAL: 'text-primary',
  WARNING: 'text-amber-600',
  OVERDUE: 'text-rose-600',
};

export function getAgeingTextClass(days: number | string | null | undefined): string {
  return TEXT_CLASS[getAgeingLevel(days)];
}

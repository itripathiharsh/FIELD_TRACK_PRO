/**
 * Money helpers. Amounts travel over the wire as decimal strings (the backend
 * uses Decimal with 2 places) and are never summed as floating point: input is
 * parsed into integer paise, arithmetic is done on integers, and the result is
 * rendered back to an exact fixed 2-decimal string.
 */

/** Largest amount the backend accepts (9999999999.99) in paise. */
export const MAX_PAISE = 999_999_999_999;

const AMOUNT_INPUT_RE = /^(\d+)(?:\.(\d{0,2}))?$/;

export type ParsedAmount =
  | { ok: true; paise: number }
  | { ok: false; reason: 'empty' | 'invalid' | 'too_many_decimals' | 'too_large' };

/** Parse a user-typed amount ("12", "12.3", "12.34") into integer paise. Rejects >2 decimals. */
export function parseAmountToPaise(raw: string | null | undefined): ParsedAmount {
  const s = (raw ?? '').trim();
  if (s === '') return { ok: false, reason: 'empty' };
  if (/^\d+\.\d{3,}$/.test(s)) return { ok: false, reason: 'too_many_decimals' };
  const m = AMOUNT_INPUT_RE.exec(s);
  if (!m) return { ok: false, reason: 'invalid' };
  const rupees = Number(m[1]);
  if (!Number.isSafeInteger(rupees) || rupees > MAX_PAISE / 100) return { ok: false, reason: 'too_large' };
  const paise = rupees * 100 + Number((m[2] ?? '').padEnd(2, '0') || '0');
  if (paise > MAX_PAISE) return { ok: false, reason: 'too_large' };
  return { ok: true, paise };
}

/**
 * Clamp a typed value to at most 2 decimals while the user types (drops extra
 * digits, keeps only digits and a single dot). Returns '' for non-numeric input.
 */
export function clampAmountInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, '');
  const firstDot = cleaned.indexOf('.');
  if (firstDot === -1) return cleaned;
  const whole = cleaned.slice(0, firstDot) || '0';
  const frac = cleaned.slice(firstDot + 1).replace(/\./g, '').slice(0, 2);
  return `${whole}.${frac}`;
}

/** Integer paise -> exact "123.45" (no grouping). Negative values keep their sign. */
export function paiseToAmountString(paise: number): string {
  const neg = paise < 0;
  const abs = Math.abs(Math.round(paise));
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, '0');
  return `${neg ? '-' : ''}${whole}.${frac}`;
}

/**
 * Backend decimals may arrive as "100.0000"; trim zero-only extra decimals to
 * a clean 2-decimal string. Values that genuinely need more precision are
 * returned unchanged so the validator can reject them.
 */
export function normalizeAmountString(raw: string): string {
  const s = (raw ?? '').trim();
  const m = /^(\d+)(?:\.(\d*))?$/.exec(s);
  if (!m) return s;
  const frac = m[2] ?? '';
  if (frac.length > 2 && /^0+$/.test(frac.slice(2))) return `${m[1]}.${frac.slice(0, 2)}`;
  if (frac.length === 0) return `${m[1]}.00`;
  if (frac.length === 1) return `${m[1]}.${frac}0`;
  return s;
}

/** Sum integer paise values exactly. */
export function sumPaise(values: number[]): number {
  return values.reduce((acc, v) => acc + v, 0);
}

function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  return `${rest},${last3}`;
}

/**
 * Normalise a decimal string/number to "[-]whole.ff" rounding half away from
 * zero on the decimal text itself (no binary float involved for strings).
 */
function toFixed2(value: string | number): string | null {
  let s: string;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    s = Math.abs(value) < 1e21 ? value.toFixed(8) : String(value);
  } else {
    s = value.trim().replace(/,/g, '');
  }
  const m = /^([+-])?(\d+)?(?:\.(\d*))?$/.exec(s);
  if (!m || (m[2] === undefined && !m[3])) return null;
  const neg = m[1] === '-';
  let whole = m[2] ?? '0';
  const frac = (m[3] ?? '').padEnd(3, '0');
  let cents = Number(frac.slice(0, 2));
  if (Number(frac[2]) >= 5) cents += 1;
  if (cents === 100) {
    cents = 0;
    const chars = whole.split('');
    let i = chars.length - 1;
    while (i >= 0) {
      if (chars[i] === '9') {
        chars[i] = '0';
        i -= 1;
      } else {
        chars[i] = String(Number(chars[i]) + 1);
        break;
      }
    }
    whole = i < 0 ? `1${chars.join('')}` : chars.join('');
  }
  whole = whole.replace(/^0+(?=\d)/, '');
  const isZero = /^0*$/.test(whole) && cents === 0;
  return `${neg && !isZero ? '-' : ''}${whole}.${String(cents).padStart(2, '0')}`;
}

/**
 * The one money formatter: rupee sign, Indian digit grouping, always exactly
 * 2 decimals. null / undefined / empty / unparseable -> '—' (never a made-up ₹0.00).
 */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const fixed = toFixed2(value);
  if (fixed === null) return '—';
  const neg = fixed.startsWith('-');
  const [whole, frac] = fixed.replace('-', '').split('.');
  return `${neg ? '-' : ''}₹${groupIndian(whole)}.${frac}`;
}

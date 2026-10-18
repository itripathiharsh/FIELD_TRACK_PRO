import { describe, expect, it } from 'vitest';
import {
  clampAmountInput,
  formatMoney,
  parseAmountToPaise,
  paiseToAmountString,
  sumPaise,
} from './money';

describe('parseAmountToPaise', () => {
  it('parses whole and decimal amounts exactly', () => {
    expect(parseAmountToPaise('12.34')).toEqual({ ok: true, paise: 1234 });
    expect(parseAmountToPaise('12.3')).toEqual({ ok: true, paise: 1230 });
    expect(parseAmountToPaise('12')).toEqual({ ok: true, paise: 1200 });
    expect(parseAmountToPaise('0.07')).toEqual({ ok: true, paise: 7 });
    expect(parseAmountToPaise('.5')).toEqual({ ok: false, reason: 'invalid' });
  });
  it('rejects more than 2 decimals, negatives, junk and absurd sizes', () => {
    expect(parseAmountToPaise('1.234')).toEqual({ ok: false, reason: 'too_many_decimals' });
    expect(parseAmountToPaise('-1')).toEqual({ ok: false, reason: 'invalid' });
    expect(parseAmountToPaise('1e3')).toEqual({ ok: false, reason: 'invalid' });
    expect(parseAmountToPaise('')).toEqual({ ok: false, reason: 'empty' });
    expect(parseAmountToPaise('99999999999')).toEqual({ ok: false, reason: 'too_large' });
  });
  it('0.1 + 0.2 is exactly 0.30', () => {
    const a = parseAmountToPaise('0.1');
    const b = parseAmountToPaise('0.2');
    if (!a.ok || !b.ok) throw new Error('parse failed');
    expect(0.1 + 0.2).not.toBe(0.3); // the float bug this avoids
    expect(paiseToAmountString(sumPaise([a.paise, b.paise]))).toBe('0.30');
  });
  it('sums many awkward amounts exactly', () => {
    const parts = Array.from({ length: 10 }, () => '0.10').map((s) => {
      const r = parseAmountToPaise(s);
      if (!r.ok) throw new Error('x');
      return r.paise;
    });
    expect(paiseToAmountString(sumPaise(parts))).toBe('1.00');
  });
});

describe('clampAmountInput', () => {
  it('limits to 2 decimals and strips junk', () => {
    expect(clampAmountInput('12.345')).toBe('12.34');
    expect(clampAmountInput('1.2.3')).toBe('1.23');
    expect(clampAmountInput('abc')).toBe('');
    expect(clampAmountInput('-5')).toBe('5');
    expect(clampAmountInput('7.')).toBe('7.');
    expect(clampAmountInput('.5')).toBe('0.5');
  });
});

describe('paiseToAmountString', () => {
  it('round-trips', () => {
    for (const s of ['0.01', '1.00', '123.45', '9999999999.99']) {
      const r = parseAmountToPaise(s);
      if (!r.ok) throw new Error(s);
      expect(paiseToAmountString(r.paise)).toBe(s);
    }
  });
});

describe('formatMoney', () => {
  it('uses Indian grouping and always 2 decimals', () => {
    expect(formatMoney('1234567.5')).toBe('₹12,34,567.50');
    expect(formatMoney(100)).toBe('₹100.00');
    expect(formatMoney('0')).toBe('₹0.00');
    expect(formatMoney('99999.999')).toBe('₹1,00,000.00');
    expect(formatMoney('-1500.5')).toBe('-₹1,500.50');
    expect(formatMoney('12345678901234.56')).toBe('₹1,23,45,67,89,01,234.56');
  });
  it('shows a dash for missing values, not zero', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined)).toBe('—');
    expect(formatMoney('')).toBe('—');
    expect(formatMoney('abc')).toBe('—');
    expect(formatMoney(NaN)).toBe('—');
  });
});

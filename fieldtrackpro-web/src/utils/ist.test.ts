import { describe, expect, it } from 'vitest';
import { formatCalendarDate, formatIstDate, formatIstDateTime, formatIstTime, formatMonthLabel } from './ist';
import { filenameFromContentDisposition } from './download';

describe('IST formatting', () => {
  it('a visit at 20:03 UTC on 30 Sep is 01 Oct 01:33 in IST', () => {
    expect(formatIstDate('2026-09-30T20:03:00Z')).toBe('01/10/2026');
    expect(formatIstTime('2026-09-30T20:03:00Z')).toBe('01:33');
    expect(formatIstDateTime('2026-09-30T20:03:00+00:00')).toBe('01/10/2026 01:33');
  });

  it('18:29 UTC is still the same IST day, 18:30 UTC is the next one', () => {
    expect(formatIstDate('2026-09-30T18:29:59Z')).toBe('30/09/2026');
    expect(formatIstDate('2026-09-30T18:30:00Z')).toBe('01/10/2026');
  });

  it('handles empty / invalid input without throwing', () => {
    expect(formatIstDate(null)).toBe('-');
    expect(formatIstDate('not a date')).toBe('-');
    expect(formatIstDateTime(undefined)).toBe('-');
  });

  it('plain calendar dates are not shifted by any time zone', () => {
    expect(formatCalendarDate('2026-09-30')).toBe('30/09/2026');
    expect(formatCalendarDate(null)).toBe('-');
    expect(formatMonthLabel('2026-09')).toBe('September 2026');
  });
});

describe('Content-Disposition parsing', () => {
  it('reads quoted, unquoted and RFC5987 file names', () => {
    expect(filenameFromContentDisposition('attachment; filename="Outstanding_20261011_1432_filtered.xlsx"')).toBe('Outstanding_20261011_1432_filtered.xlsx');
    expect(filenameFromContentDisposition('attachment; filename=Report.pdf')).toBe('Report.pdf');
    expect(filenameFromContentDisposition("attachment; filename*=UTF-8''Rep%20ort.pdf")).toBe('Rep ort.pdf');
    expect(filenameFromContentDisposition(null)).toBeNull();
    expect(filenameFromContentDisposition('inline')).toBeNull();
  });
});

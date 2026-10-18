import { describe, expect, it } from 'vitest';
import { getAgeingLevel, getAgeingTextClass } from './ageing';

describe('getAgeingLevel', () => {
  it.each([
    [0, 'NORMAL'],
    [20, 'NORMAL'],
    [21, 'WARNING'],
    [25, 'WARNING'],
    [26, 'OVERDUE'],
    [90, 'OVERDUE'],
  ])('day %i is %s', (days, level) => {
    expect(getAgeingLevel(days)).toBe(level);
  });

  it('accepts numeric strings and treats junk as NORMAL', () => {
    expect(getAgeingLevel('25')).toBe('WARNING');
    expect(getAgeingLevel(undefined)).toBe('NORMAL');
    expect(getAgeingLevel('abc')).toBe('NORMAL');
  });

  it('maps levels to yellow/red classes', () => {
    expect(getAgeingTextClass(21)).toContain('amber');
    expect(getAgeingTextClass(26)).toContain('rose');
    expect(getAgeingTextClass(20)).toBe('text-primary');
  });
});

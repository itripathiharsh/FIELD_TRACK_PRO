import { describe, expect, it } from 'vitest';
import { passwordStrength, utf8ByteLength, validateNewPassword } from './passwordRules';

describe('validateNewPassword', () => {
  it('accepts a normal password', () => {
    expect(validateNewPassword('Tr1cky-Passw0rd', 'old-one-123')).toEqual([]);
  });
  it('rejects fewer than 8 characters', () => {
    expect(validateNewPassword('abc123', 'x')[0]).toMatch(/at least 8/);
  });
  it('rejects more than 72 UTF-8 bytes even when under 72 characters', () => {
    const multibyte = 'é'.repeat(40); // 40 chars, 80 bytes
    expect(utf8ByteLength(multibyte)).toBe(80);
    expect(validateNewPassword(multibyte).join(' ')).toMatch(/72 bytes/);
    expect(validateNewPassword('a'.repeat(72))).toEqual([]);
    expect(validateNewPassword('a'.repeat(73)).join(' ')).toMatch(/72 bytes/);
  });
  it('counts 4-byte code points correctly', () => {
    expect(utf8ByteLength('😀')).toBe(4);
    expect(utf8ByteLength('a€')).toBe(4);
  });
  it('rejects a new password equal to the current one', () => {
    expect(validateNewPassword('SamePassw0rd', 'SamePassw0rd').join(' ')).toMatch(/different/);
  });
});

describe('passwordStrength', () => {
  it('grades by length and variety', () => {
    expect(passwordStrength('short').label).toBe('Too short');
    expect(passwordStrength('password').label).toBe('Weak');
    expect(passwordStrength('aaaaaaaaaa').label).toBe('Weak');
    expect(passwordStrength('abcdefgh1').label).toBe('Weak');
    expect(passwordStrength('Abcdefgh1').label).toBe('Fair');
    expect(passwordStrength('Abcdefgh1!xy').level).toBeGreaterThanOrEqual(3);
    expect(passwordStrength('Correct-Horse-Battery-9').label).toBe('Strong');
  });
});

/**
 * Client-side password rules. They mirror the backend (schemas/user.py,
 * UserUpdatePassword): 8-128 characters, at most 72 bytes of UTF-8 (bcrypt's
 * limit - extra bytes would be silently ignored), and different from the
 * current password. The server remains the authority; these checks only give
 * instant feedback.
 */
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;
export const PASSWORD_MAX_BYTES = 72;

/** UTF-8 byte length without relying on TextEncoder (absent in some test/old environments). */
export function utf8ByteLength(value: string): number {
  let bytes = 0;
  for (const ch of value) {
    const cp = ch.codePointAt(0) ?? 0;
    if (cp <= 0x7f) bytes += 1;
    else if (cp <= 0x7ff) bytes += 2;
    else if (cp <= 0xffff) bytes += 3;
    else bytes += 4;
  }
  return bytes;
}

/** Human-readable problems with a proposed new password (empty array = acceptable). */
export function validateNewPassword(newPassword: string, currentPassword?: string): string[] {
  const errors: string[] = [];
  if ([...newPassword].length < PASSWORD_MIN_LENGTH) {
    errors.push(`Use at least ${PASSWORD_MIN_LENGTH} characters.`);
  }
  if ([...newPassword].length > PASSWORD_MAX_LENGTH) {
    errors.push(`Use at most ${PASSWORD_MAX_LENGTH} characters.`);
  }
  if (utf8ByteLength(newPassword) > PASSWORD_MAX_BYTES) {
    errors.push(`Too long: passwords can be at most ${PASSWORD_MAX_BYTES} bytes (non-English characters count as 2-4 bytes each).`);
  }
  if (currentPassword !== undefined && currentPassword !== '' && newPassword === currentPassword) {
    errors.push('The new password must be different from the current one.');
  }
  return errors;
}

export type PasswordStrengthLevel = 0 | 1 | 2 | 3 | 4;

export interface PasswordStrength {
  level: PasswordStrengthLevel;
  label: 'Too short' | 'Weak' | 'Fair' | 'Good' | 'Strong';
}

const COMMON = new Set(['password', 'password1', '12345678', '123456789', 'qwertyuiop', 'iloveyou', 'admin123', 'welcome1', 'fieldtrack']);

/** Rough, dependency-free strength hint (length + character variety). Advisory only. */
export function passwordStrength(password: string): PasswordStrength {
  const len = [...password].length;
  if (len < PASSWORD_MIN_LENGTH) return { level: 0, label: 'Too short' };
  if (COMMON.has(password.toLowerCase())) return { level: 1, label: 'Weak' };
  let classes = 0;
  if (/[a-z]/.test(password)) classes += 1;
  if (/[A-Z]/.test(password)) classes += 1;
  if (/\d/.test(password)) classes += 1;
  if (/[^A-Za-z0-9]/.test(password)) classes += 1;
  let score = classes + (len >= 12 ? 1 : 0) + (len >= 16 ? 1 : 0);
  if (/^(.)\1+$/.test(password)) score = 1;
  if (score <= 2) return { level: 1, label: 'Weak' };
  if (score === 3) return { level: 2, label: 'Fair' };
  if (score === 4) return { level: 3, label: 'Good' };
  return { level: 4, label: 'Strong' };
}

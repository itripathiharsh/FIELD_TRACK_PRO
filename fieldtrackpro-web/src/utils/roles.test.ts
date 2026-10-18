import { describe, expect, it, vi } from 'vitest';
import { isAdmin, isSuperAdmin, isValidRole, resolveRole, roleLabel, sanitizeUser, VALID_ROLES } from './roles';
import { ADMIN_USER, EMPLOYEE_USER } from '../test/utils';
import type { User } from '../types';

const SUPER_ADMIN_USER: User = { ...ADMIN_USER, role: 'SUPER_ADMIN' };

describe('roles', () => {
  it('only SUPER_ADMIN, ADMIN and EMPLOYEE are valid', () => {
    expect([...VALID_ROLES]).toEqual(['SUPER_ADMIN', 'ADMIN', 'EMPLOYEE']);
    expect(isValidRole('SUPER_ADMIN')).toBe(true);
    expect(isValidRole('ADMIN')).toBe(true);
    expect(isValidRole('EMPLOYEE')).toBe(true);
    for (const bad of ['MANAGER', 'admin', 'super_admin', 'SUPERUSER', '', null, undefined, 1]) {
      expect(isValidRole(bad)).toBe(false);
    }
  });

  it('resolves unexpected roles to EMPLOYEE', () => {
    expect(resolveRole('MANAGER')).toBe('EMPLOYEE');
    expect(resolveRole('admin')).toBe('EMPLOYEE');
    expect(resolveRole('ADMIN')).toBe('ADMIN');
    expect(resolveRole('SUPER_ADMIN')).toBe('SUPER_ADMIN');
  });

  it('isAdmin is true for ADMIN and SUPER_ADMIN (a strict superset) and nothing else', () => {
    expect(isAdmin(ADMIN_USER)).toBe(true);
    expect(isAdmin(SUPER_ADMIN_USER)).toBe(true);
    expect(isAdmin(EMPLOYEE_USER)).toBe(false);
    expect(isAdmin({ role: 'MANAGER' } as unknown as User)).toBe(false);
    expect(isAdmin(null)).toBe(false);
  });

  it('isSuperAdmin is true only for an exact SUPER_ADMIN', () => {
    expect(isSuperAdmin(SUPER_ADMIN_USER)).toBe(true);
    expect(isSuperAdmin(ADMIN_USER)).toBe(false);
    expect(isSuperAdmin(EMPLOYEE_USER)).toBe(false);
    expect(isSuperAdmin({ role: 'super_admin' } as unknown as User)).toBe(false);
    expect(isSuperAdmin(undefined)).toBe(false);
  });

  it('roleLabel gives a human label and never invents privilege', () => {
    expect(roleLabel('SUPER_ADMIN')).toBe('Super Admin');
    expect(roleLabel('ADMIN')).toBe('Admin');
    expect(roleLabel('EMPLOYEE')).toBe('Employee');
    expect(roleLabel('nonsense')).toBe('Employee');
  });

  it('sanitizeUser downgrades an unexpected role', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const out = sanitizeUser({ ...ADMIN_USER, role: 'MANAGER' as unknown as User['role'] });
    expect(out.role).toBe('EMPLOYEE');
    expect(sanitizeUser(ADMIN_USER)).toBe(ADMIN_USER);
    expect(sanitizeUser(SUPER_ADMIN_USER)).toBe(SUPER_ADMIN_USER);
  });
});

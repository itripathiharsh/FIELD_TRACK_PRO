import type { User, UserRole } from '../types';

/**
 * Authorization roles, least to most privileged: EMPLOYEE < ADMIN < SUPER_ADMIN.
 * Business job titles (e.g. "Sales Manager" in an employee's working_profile) are display-only and
 * must never be used for authorization. The backend enforces every rule; the helpers below only
 * decide what the UI shows.
 */
export const VALID_ROLES: readonly UserRole[] = ['SUPER_ADMIN', 'ADMIN', 'EMPLOYEE', 'ACCOUNTANT'];

export function isValidRole(role: unknown): role is UserRole {
  return typeof role === 'string' && (VALID_ROLES as readonly string[]).includes(role);
}

/**
 * Least-privilege role resolution: anything that is not exactly 'SUPER_ADMIN', 'ADMIN' or
 * 'EMPLOYEE' (including 'MANAGER', lowercase variants, null) is EMPLOYEE.
 */
export function resolveRole(role: unknown): UserRole {
  return isValidRole(role) ? role : 'EMPLOYEE';
}

/** True for ADMIN and SUPER_ADMIN: the global-access roles (a Super Admin is a strict superset of Admin). */
export function isAdmin(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN';
}

/**
 * True only for ACCOUNTANT: web-only, READ-ONLY access to Reports & Collections (financial reports,
 * collections, exports). Never an administrator and never a field employee.
 */
export function isAccountant(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'ACCOUNTANT';
}

/** Who may open Reports & Collections: administrators and the read-only accountant. */
export function canViewFinance(user: Pick<User, 'role'> | null | undefined): boolean {
  return isAdmin(user) || isAccountant(user);
}

/** The only pages an accountant may open; everything else redirects to Reports & Collections. */
export const ACCOUNTANT_PATHS: readonly string[] = ['/reports', '/profile'];

/** True only for an exact SUPER_ADMIN: the sole role that may manage roles. */
export function isSuperAdmin(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'SUPER_ADMIN';
}

const ROLE_LABELS: Record<UserRole, string> = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN: 'Admin',
  EMPLOYEE: 'Employee',
  ACCOUNTANT: 'Accountant',
};

/** Human label for a role value (unknown values are shown as Employee, matching resolveRole). */
export function roleLabel(role: unknown): string {
  return ROLE_LABELS[resolveRole(role)];
}

/** Returns a copy of the user with an unexpected role downgraded to EMPLOYEE. */
export function sanitizeUser(user: User): User {
  if (isValidRole(user.role)) return user;
  // eslint-disable-next-line no-console
  console.warn(`Unexpected role "${String(user.role)}" received; treating as EMPLOYEE (least privilege).`);
  return { ...user, role: 'EMPLOYEE' };
}

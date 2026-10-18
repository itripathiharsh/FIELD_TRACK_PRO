import type { Employee, UserRole } from '../../types';
import { isAdmin, isSuperAdmin, resolveRole } from '../../utils/roles';

/**
 * Whether the signed-in user may be OFFERED the reset-password action for this employee. This only decides
 * visibility - the backend independently re-checks every rule and is the real authority:
 *   Admin       -> EMPLOYEE accounts only
 *   Super Admin -> EMPLOYEE and ADMIN accounts
 *   nobody      -> their own account, a Super Admin account, or a disabled account
 */
export function canOfferPasswordReset(
  actor: { id: string; role: string } | null | undefined,
  employee: Pick<Employee, 'user_id' | 'user'>,
): boolean {
  if (!actor || !isAdmin(actor as never)) return false;
  if (employee.user_id === actor.id) return false;
  if (employee.user && employee.user.is_active === false) return false;
  const targetRole = resolveRole(employee.user?.role);
  if (targetRole === 'SUPER_ADMIN') return false;
  if (targetRole === 'ADMIN') return isSuperAdmin(actor as never);
  return true;
}

/** Role transitions the backend accepts (one step at a time). Mirrors the server; the server enforces. */
export const ALLOWED_NEXT_ROLES: Record<UserRole, UserRole[]> = {
  EMPLOYEE: ['ADMIN'],
  ADMIN: ['EMPLOYEE', 'SUPER_ADMIN'],
  SUPER_ADMIN: ['ADMIN'],
};

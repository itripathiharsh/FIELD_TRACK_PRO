import React from 'react';
import { ShieldCheck, Shield, User as UserIcon, Calculator } from 'lucide-react';
import type { UserRole } from '../../types';
import { resolveRole, roleLabel } from '../../utils/roles';

const STYLES: Record<UserRole, string> = {
  SUPER_ADMIN: 'bg-secondary-container text-primary border-secondary-fixed-dim',
  ADMIN: 'bg-primary-container text-on-primary-container border-primary-container',
  EMPLOYEE: 'bg-surface-container text-on-surface-variant border-outline-variant',
  ACCOUNTANT: 'bg-surface-container-high text-on-surface border-outline-variant',
};

const ICONS: Record<UserRole, React.ElementType> = {
  SUPER_ADMIN: ShieldCheck,
  ADMIN: Shield,
  EMPLOYEE: UserIcon,
  ACCOUNTANT: Calculator,
};

/** Compact role pill used wherever an account's role is shown (profile header, dialogs). */
export const RoleBadge: React.FC<{ role: unknown }> = ({ role }) => {
  const resolved = resolveRole(role);
  const Icon = ICONS[resolved];
  return (
    <span
      data-testid="role-badge"
      className={`inline-flex items-center gap-space-1.5 rounded-full px-3 py-1 text-[12px] font-label-md uppercase tracking-wider font-semibold border ${STYLES[resolved]}`}
    >
      <Icon className="w-3.5 h-3.5 shrink-0" />
      {roleLabel(resolved)}
    </span>
  );
};

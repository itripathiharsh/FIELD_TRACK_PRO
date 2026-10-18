import React, { useId, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { Employee, UserRole } from '../../types';
import { isSuperAdmin, resolveRole, roleLabel } from '../../utils/roles';
import { errorMessage } from '../../utils/errors';
import { Button } from '../ui/Button';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Input } from '../ui/Input';
import { Modal } from '../ui/Modal';
import { Select } from '../ui/Select';
import { RoleBadge } from './RoleBadge';
import { ALLOWED_NEXT_ROLES } from './securityRules';

const IMPACT: Record<string, string> = {
  'EMPLOYEE>ADMIN':
    'They will gain administrator access: every employee, customer, payment and report in the system.',
  'ADMIN>EMPLOYEE':
    'They will lose administrator access immediately and see only their own assigned work.',
  'ADMIN>SUPER_ADMIN':
    'They will become a Super Admin: full administrator access PLUS the power to change roles, including promoting and demoting other Super Admins.',
  'SUPER_ADMIN>ADMIN':
    'They will lose the ability to manage roles and Super Admin accounts immediately. They remain an Admin.',
};

interface Props {
  employee: Employee;
  /** Called after a successful change with the new role (parent re-reads the profile). */
  onChanged?: (newRole: UserRole) => void;
}

/**
 * Super-Admin-only "Change Role" action. Renders nothing for anyone else (the backend refuses the
 * call regardless). Requires the acting Super Admin's own password (re-authentication) and, for any
 * change that grants or removes SUPER_ADMIN, an explicit confirmation checkbox.
 */
export const ChangeRoleControl: React.FC<Props> = ({ employee, onChanged }) => {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [newRole, setNewRole] = useState<UserRole | ''>('');
  const [password, setPassword] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const confirmId = useId();

  if (!isSuperAdmin(user) || !employee.user) return null;

  const currentRole = resolveRole(employee.user.role);
  const options = ALLOWED_NEXT_ROLES[currentRole];
  const isSelf = employee.user_id === user?.id;
  const selected = newRole || options[0];
  const involvesSuper = currentRole === 'SUPER_ADMIN' || selected === 'SUPER_ADMIN';
  const impact = IMPACT[`${currentRole}>${selected}`];

  const reset = () => {
    setPassword('');
    setConfirmed(false);
    setError(null);
    setNewRole('');
  };

  const open = () => {
    reset();
    setNotice(null);
    setIsOpen(true);
  };

  const close = () => {
    reset(); // the password never outlives the dialog
    setIsOpen(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await apiClient.changeUserRole(employee.user_id, {
        role: selected,
        current_password: password,
        confirm: involvesSuper ? confirmed : false,
      });
      setIsOpen(false);
      reset();
      if (isSelf) {
        // The server ended this account's sessions with the role change. Sign out locally so the
        // UI cannot keep showing privileges the account no longer has; the next login picks up the new role.
        await logout();
        return;
      }
      setNotice(`Role changed to ${roleLabel(selected)}. Their sessions were signed out so it applies immediately.`);
      onChanged?.(selected);
    } catch (err) {
      setError(errorMessage(err, 'The role could not be changed. Please try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSubmit = password.length > 0 && (!involvesSuper || confirmed) && !isSubmitting;

  return (
    <>
      <Button variant="outline" size="sm" icon={ShieldCheck} onClick={open}>
        Change Role
      </Button>
      {notice && (
        <p role="status" className="text-xs text-primary font-medium w-full">
          {notice}
        </p>
      )}

      <Modal
        isOpen={isOpen}
        onClose={close}
        title="Change role"
        subtitle={employee.full_name}
        size="md"
        disableClose={isSubmitting}
      >
        <form onSubmit={submit} className="space-y-space-4" autoComplete="off">
          <div className="flex items-center gap-space-2 text-xs text-on-surface-variant">
            Current role: <RoleBadge role={currentRole} />
          </div>

          <Select
            id="new-role"
            label="New role"
            value={selected}
            onChange={(e) => {
              setNewRole(e.target.value as UserRole);
              setConfirmed(false);
            }}
            disabled={isSubmitting}
          >
            {options.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </Select>

          {impact && (
            <p className="text-xs p-space-3 rounded-lg bg-secondary-fixed/40 border border-secondary-fixed-dim text-on-surface">
              <strong>Impact:</strong> {impact} Their current sessions (web and mobile) are signed out so the change applies
              immediately.
              {isSelf && ' This is your own account: you will be signed out and must sign in again.'}
            </p>
          )}

          <Input
            label="Your password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            helperText="Re-enter your own password to confirm this sensitive change."
            disabled={isSubmitting}
          />

          {involvesSuper && (
            <label htmlFor={confirmId} className="flex items-start gap-space-2 text-xs text-on-surface cursor-pointer">
              <input
                id={confirmId}
                type="checkbox"
                className="mt-0.5"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                disabled={isSubmitting}
              />
              <span>
                I understand this changes <strong>Super Admin</strong> privileges and I want to proceed.
              </span>
            </label>
          )}

          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

          <div className="flex justify-end gap-space-3">
            <Button type="button" variant="ghost" onClick={close} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" icon={ShieldCheck} isLoading={isSubmitting} disabled={!canSubmit}>
              Change role
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};

import React, { useCallback, useEffect, useState } from 'react';
import { KeyRound, LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { apiClient } from '../api/client';
import { PasswordStrengthHint } from '../components/auth/PasswordStrengthHint';
import { PASSWORD_MIN_LENGTH, validateNewPassword } from '../utils/passwordRules';
import { Employee } from '../types';

export const ProfilePage: React.FC = () => {
  const { user, logout, changePassword } = useAuth();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [isLoadingEmployee, setIsLoadingEmployee] = useState(true);
  const [employeeError, setEmployeeError] = useState<string | null>(null);

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const loadEmployee = useCallback(async () => {
    try {
      setIsLoadingEmployee(true);
      const emp = await apiClient.getMyEmployeeProfile();
      setEmployee(emp);
    } catch {
      setEmployeeError('No employee profile found for this account.');
      setEmployee(null);
    } finally {
      setIsLoadingEmployee(false);
    }
  }, []);

  useEffect(() => {
    loadEmployee();
  }, [loadEmployee]);

  const handleLogout = () => {
    void logout();
  };

  /**
   * FT-023: self-service password change.
   *
   * The backend revokes every outstanding refresh token on success, so other
   * devices are signed out. That consequence is stated to the user rather than
   * happening invisibly.
   */
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus(null);

    const problems = validateNewPassword(newPassword, oldPassword);
    if (problems.length > 0) {
      setStatus({ ok: false, text: problems[0] });
      return;
    }
    if (newPassword !== confirmPassword) {
      setStatus({ ok: false, text: 'The new passwords do not match.' });
      return;
    }

    setIsSaving(true);
    try {
      const result = await changePassword(oldPassword, newPassword);
      setStatus({
        ok: true,
        text:
          result === 'reauthenticated'
            ? 'Password updated. Sessions on your other devices have been signed out.'
            : 'Password updated. Please sign in again with your new password.',
      });
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setStatus({
        ok: false,
        text: err instanceof Error ? err.message : 'Could not update password.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-space-6 max-w-2xl font-body-md text-on-surface">
      <PageHeader
        title="User Profile"
        subtitle="Your account details and session security."
      />

      <Card variant="default" className="space-y-space-6">
        <div className="flex items-center gap-space-4 border-b border-surface-container-highest pb-space-6">
          <div className="w-14 h-14 rounded-full bg-primary-container text-on-primary-container border border-primary-fixed-dim flex items-center justify-center font-headline-lg text-xl uppercase font-bold shrink-0">
            {user?.full_name?.charAt(0) || '?'}
          </div>
          <div>
            <h2 className="font-headline-sm text-lg font-bold text-primary">
              {user?.full_name || 'Unknown user'}
            </h2>
            <div className="mt-1.5">
              {user?.role && <StatusBadge status={user.role} size="sm" showDot={false} />}
            </div>
          </div>
        </div>

        <div className="space-y-space-4 font-body-md text-xs">
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
              Account ID
            </p>
            <p className="text-on-surface font-mono mt-0.5">{user?.id || '—'}</p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
              Email Address
            </p>
            <p className="text-on-surface font-medium mt-0.5">{user?.email || '—'}</p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
              Mobile Phone
            </p>
            <p className="text-on-surface font-medium mt-0.5">{user?.mobile_number || 'Not set'}</p>
          </div>
        </div>

        <div className="pt-space-4 border-t border-surface-container-highest">
          <Button variant="danger" size="md" icon={LogOut} onClick={handleLogout} className="w-full">
            Sign Out Session
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Employee Profile</CardTitle>
          <CardSubtitle>Your field representative profile from the server.</CardSubtitle>
        </CardHeader>
        <div className="p-space-5">
          {isLoadingEmployee ? (
            <div className="flex items-center justify-center h-32" role="status">
              <div className="w-8 h-8 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
            </div>
          ) : employeeError ? (
            <ErrorBanner message={employeeError} onRetry={loadEmployee} />
          ) : employee ? (
            <div className="space-y-space-4">
              <div>
                <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
                  Full Name
                </p>
                <p className="text-on-surface font-medium mt-0.5">{employee.full_name}</p>
              </div>
              <div>
                <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
                  Employee Code
                </p>
                <p className="text-on-surface font-medium mt-0.5">{employee.employee_code || '—'}</p>
              </div>
              <div>
                <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
                  Territory
                </p>
                <p className="text-on-surface font-medium mt-0.5">{employee.effective_territory_name || employee.territory_id || 'Unassigned'}</p>
              </div>
              <div>
                <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
                  Contact Email
                </p>
                <p className="text-on-surface font-medium mt-0.5">{employee.user?.email || '—'}</p>
              </div>
              <div>
                <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">
                  Contact Phone
                </p>
                <p className="text-on-surface font-medium mt-0.5">{employee.user?.mobile_number || '—'}</p>
              </div>
            </div>
          ) : (
            <EmptyState title="No employee profile" subtitle="No employee profile is linked to this account." />
          )}
        </div>
      </Card>

      <Card variant="default" className="space-y-space-4">
        <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
          <KeyRound className="w-5 h-5 text-primary" />
          <h3 className="font-headline-sm text-base font-bold text-primary">Change Password</h3>
        </div>

        {status && (
          <div
            role="status"
            className={`p-space-3 rounded-lg border font-body-md text-xs ${
              status.ok
                ? 'bg-primary-container text-on-primary-container border-primary-container'
                : 'bg-error-container text-on-error-container border-error'
            }`}
          >
            {status.text}
          </div>
        )}

        <form onSubmit={handleChangePassword} className="space-y-space-4">
          <Input
            label="Current Password"
            type="password"
            required
            autoComplete="current-password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
          />
          <Input
            label="New Password"
            type="password"
            required
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            helperText={`Minimum ${PASSWORD_MIN_LENGTH} characters, at most 72 bytes.`}
          />
          <PasswordStrengthHint password={newPassword} />
          <Input
            label="Confirm New Password"
            type="password"
            required
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <p className="font-caption text-xs text-on-surface-variant">
            Changing your password signs you out of every other device.
          </p>
          <Button
            type="submit"
            variant="secondary"
            size="md"
            icon={KeyRound}
            isLoading={isSaving}
            disabled={!oldPassword || !newPassword || !confirmPassword}
          >
            Update Password
          </Button>
        </form>
      </Card>
    </div>
  );
};

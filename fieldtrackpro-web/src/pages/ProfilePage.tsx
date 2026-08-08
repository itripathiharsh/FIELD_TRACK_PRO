import React, { useState } from 'react';
import { KeyRound, LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { StatusBadge } from '../components/ui/StatusBadge';
import { apiClient } from '../api/client';

const MIN_PASSWORD_LENGTH = 8;

export const ProfilePage: React.FC = () => {
  const { user, logout } = useAuth();

  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [isSaving, setIsSaving] = useState(false);

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

    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setStatus({ ok: false, text: `New password must be at least ${MIN_PASSWORD_LENGTH} characters.` });
      return;
    }
    if (newPassword !== confirmPassword) {
      setStatus({ ok: false, text: 'The new passwords do not match.' });
      return;
    }
    if (newPassword === oldPassword) {
      setStatus({ ok: false, text: 'The new password must be different from the current one.' });
      return;
    }

    setIsSaving(true);
    try {
      await apiClient.changePassword(oldPassword, newPassword);
      setStatus({
        ok: true,
        text: 'Password updated. Sessions on your other devices have been signed out.',
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
            minLength={MIN_PASSWORD_LENGTH}
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            helperText={`Minimum ${MIN_PASSWORD_LENGTH} characters.`}
          />
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

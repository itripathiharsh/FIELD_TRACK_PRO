import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { PasswordStrengthHint } from '../components/auth/PasswordStrengthHint';
import { PASSWORD_MIN_LENGTH, validateNewPassword } from '../utils/passwordRules';

/**
 * Full-screen "Set a new password" page. Rendered by the route guards instead of
 * the requested page whenever the user has must_change_password === true (from
 * /auth/me) or any API call answered 403 PASSWORD_CHANGE_REQUIRED. The URL is
 * left untouched, so after a successful change the user simply lands on the page
 * they were trying to open.
 */
export const ChangePasswordRequiredPage: React.FC = () => {
  const { user, logout, changePassword } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const ruleErrors = next ? validateNewPassword(next, current) : [];
  const mismatch = confirm !== '' && confirm !== next;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const problems = validateNewPassword(next, current);
    if (problems.length > 0) {
      setError(problems[0]);
      return;
    }
    if (next !== confirm) {
      setError('The new passwords do not match.');
      return;
    }
    setIsSaving(true);
    try {
      const result = await changePassword(current, next);
      if (result === 'signed_out') {
        navigate('/login', { replace: true, state: { reason: 'password_changed' } });
      }
      // 'reauthenticated': must_change_password is now false, so the guard renders the requested page.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the password. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main className="min-h-screen bg-background flex items-center justify-center px-4 py-10 text-on-surface">
      <form
        onSubmit={handleSubmit}
        aria-labelledby="set-password-heading"
        className="w-full max-w-md bg-surface rounded-xl border border-outline-variant shadow-md p-space-6 space-y-space-4"
      >
        <div className="flex items-center gap-space-3">
          <KeyRound className="w-7 h-7 text-secondary shrink-0" aria-hidden="true" />
          <div>
            <h1 id="set-password-heading" className="font-headline-md text-headline-md text-primary">
              Set a new password
            </h1>
            <p className="font-caption text-caption text-on-surface-variant">
              {user?.full_name ? `${user.full_name}, you` : 'You'} are using a temporary password. Choose a new one to
              continue.
            </p>
          </div>
        </div>

        {error && <ErrorBanner message={error} />}

        <Input
          label="Current Password"
          type="password"
          required
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <div>
          <Input
            label="New Password"
            type="password"
            required
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            error={ruleErrors[0]}
            helperText={`At least ${PASSWORD_MIN_LENGTH} characters, different from the current password.`}
          />
          <PasswordStrengthHint password={next} />
        </div>
        <Input
          label="Confirm New Password"
          type="password"
          required
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={mismatch ? 'The new passwords do not match.' : undefined}
        />

        <Button
          type="submit"
          variant="primary"
          className="w-full"
          isLoading={isSaving}
          disabled={!current || !next || !confirm || ruleErrors.length > 0 || mismatch}
        >
          Set new password
        </Button>

        <p className="text-center text-xs text-on-surface-variant">
          Not you?{' '}
          <button type="button" onClick={() => void logout()} className="text-primary underline font-semibold">
            Sign out
          </button>
        </p>
      </form>
    </main>
  );
};

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, Copy, KeyRound, ShieldAlert } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { Employee } from '../../types';
import { errorMessage } from '../../utils/errors';
import { Button } from '../ui/Button';
import { ErrorBanner } from '../ui/ErrorBanner';
import { Modal } from '../ui/Modal';
import { canOfferPasswordReset } from './securityRules';

interface Props {
  employee: Employee;
  /** Called after a successful reset (e.g. to reload the profile and show the pending-expiry status). */
  onReset?: () => void;
}

type Step = 'idle' | 'confirm' | 'secret';

/**
 * "Reset Password" action for the employee profile: confirmation dialog -> real API call -> one-time
 * display of the server-generated temporary password.
 *
 * The temporary password lives ONLY in this component's React state. It is never written to the URL,
 * localStorage/sessionStorage/IndexedDB, cookies, the console or any analytics call, and it is cleared
 * the moment the dialog closes or the component unmounts (e.g. on navigation).
 */
export const ResetPasswordControl: React.FC<Props> = ({ employee, onReset }) => {
  const { user } = useAuth();
  const [step, setStep] = useState<Step>('idle');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [expiresInMinutes, setExpiresInMinutes] = useState<number>(30);
  const [copied, setCopied] = useState(false);
  const inFlight = useRef(false);

  const clearSecret = useCallback(() => {
    setTemporaryPassword(null);
    setCopied(false);
  }, []);

  // Navigating away unmounts this component; state (including the secret) is discarded with it.
  useEffect(() => clearSecret, [clearSecret]);

  if (!canOfferPasswordReset(user, employee)) return null;

  const closeAll = () => {
    clearSecret();
    setError(null);
    setStep('idle');
  };

  const submit = async () => {
    if (inFlight.current) return; // prevent duplicate submissions
    inFlight.current = true;
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await apiClient.resetEmployeePassword(employee.id);
      setTemporaryPassword(result.temporary_password);
      setExpiresInMinutes(result.expires_in_minutes);
      setStep('secret');
      onReset?.();
    } catch (err) {
      setError(errorMessage(err, 'The password could not be reset. Please try again.'));
    } finally {
      inFlight.current = false;
      setIsSubmitting(false);
    }
  };

  const copy = async () => {
    if (!temporaryPassword) return;
    try {
      await navigator.clipboard.writeText(temporaryPassword);
      setCopied(true);
    } catch {
      setCopied(false);
      setError('Copy was blocked by the browser. Select the password above and copy it manually.');
    }
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        icon={KeyRound}
        onClick={() => {
          setError(null);
          setStep('confirm');
        }}
      >
        Reset Password
      </Button>

      <Modal
        isOpen={step === 'confirm'}
        onClose={closeAll}
        title="Reset password?"
        subtitle={employee.full_name}
        size="md"
        disableClose={isSubmitting}
      >
        <div className="space-y-space-4">
          <div className="flex gap-space-3 p-space-3 rounded-lg bg-secondary-fixed/40 border border-secondary-fixed-dim text-xs text-on-surface">
            <AlertTriangle className="w-5 h-5 shrink-0 text-primary" />
            <div className="space-y-space-1">
              <p>
                A new <strong>temporary password</strong> will be generated for {employee.full_name}. It is valid for a
                limited time and can only be used once.
              </p>
              <p>
                Their current password stops working and <strong>all of their existing sessions (web and mobile) are
                signed out</strong>. They must choose a new password the next time they sign in.
              </p>
            </div>
          </div>
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
          <div className="flex justify-end gap-space-3">
            <Button variant="ghost" onClick={closeAll} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button variant="primary" icon={KeyRound} onClick={submit} isLoading={isSubmitting}>
              Reset password
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={step === 'secret'}
        onClose={closeAll}
        title="Temporary password"
        subtitle={employee.full_name}
        size="md"
      >
        <div className="space-y-space-4" data-testid="temp-password-dialog">
          <p className="text-xs text-on-surface-variant">
            Give this password to {employee.full_name} <strong>privately</strong> (in person or a direct message).
            Do not post it in a group chat, e-mail it to others or write it where others can see it.
          </p>
          <div className="flex items-center justify-between gap-space-3 p-space-4 rounded-xl bg-surface-container-low border border-surface-container-highest">
            <code
              data-testid="temp-password-value"
              className="font-mono text-lg tracking-wider text-primary select-all break-all"
            >
              {temporaryPassword}
            </code>
            <Button variant="outline" size="sm" icon={copied ? Check : Copy} onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
          <div className="flex gap-space-3 p-space-3 rounded-lg bg-error-container/40 border border-error/30 text-xs text-on-error-container">
            <ShieldAlert className="w-5 h-5 shrink-0 text-error" />
            <div className="space-y-space-1">
              <p>
                <strong>This password will not be shown again</strong> once you close this window or refresh the page.
                If you lose it, reset the password again.
              </p>
              <p>It expires in {expiresInMinutes} minutes and stops working as soon as the employee sets a new one.</p>
            </div>
          </div>
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
          <div className="flex justify-end">
            <Button variant="primary" onClick={closeAll}>
              I have shared it - close
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
};

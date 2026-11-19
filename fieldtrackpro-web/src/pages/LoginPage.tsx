import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Lock,
  Mail,
  Smartphone,
  KeyRound,
  CheckCircle2,
  RefreshCw,
  ArrowLeft,
  Check,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { canViewAdmin as isAdminRole } from '../utils/roles';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { apiClient } from '../api/client';
import { LoginBrandPanel } from '../components/auth/LoginBrandPanel';
import { ApkDownloadCard } from '../components/auth/ApkDownloadCard';

type RecoveryStep = 'login' | 'request_otp' | 'verify_otp' | 'set_password' | 'success';

const isPhoneLike = (v: string) => v.trim() !== '' && /^[\d+\s-]+$/.test(v.trim());

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const navReason = (location.state as { reason?: string } | null)?.reason;
  const sessionExpiredNotice = navReason === 'session_expired';
  const passwordChangedNotice = navReason === 'password_changed';
  const { login } = useAuth();

  const [step, setStep] = useState<RecoveryStep>('login');

  // Input states
  const [identity, setIdentity] = useState('');
  const [password, setPassword] = useState('');

  const [otp, setOtp] = useState('');
  const [maskedDestination, setMaskedDestination] = useState<string | null>(null);
  const [deliveryChannel, setDeliveryChannel] = useState<'EMAIL' | 'SMS' | null>(null);

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  // Status & Feedback
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Resend cooldown timer
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (resendCooldown > 0) {
      timer = setTimeout(() => setResendCooldown((prev) => prev - 1), 1000);
    }
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  // Login handler
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    setIsSubmitting(true);
    try {
      const user = await login(identity.trim(), password);
      navigate(isAdminRole(user) ? '/' : '/visits', { replace: true });
    } catch (err: unknown) {
      const lowered = (err instanceof Error ? err.message : '').toLowerCase();
      if (
        (typeof err === 'object' && err !== null && (err as { code?: unknown }).code === 'AUTH_ACCOUNT_DISABLED') ||
        lowered.includes('account is disabled') ||
        lowered.includes('account disabled') ||
        lowered.includes('deactivated')
      ) {
        setError('Your account has been deactivated. Please contact your administrator.');
      } else {
        setError(
          err instanceof Error
            ? err.message
            : 'Authentication failed. Please check your credentials.',
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Step 1: Request OTP
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identity.trim()) {
      setError('Please enter your email or mobile number.');
      return;
    }
    setError(null);
    setSuccessMsg(null);
    setIsSubmitting(true);
    try {
      const resp = await apiClient.forgotPassword(identity.trim());
      setMaskedDestination(resp.destination || identity.trim());
      setDeliveryChannel(resp.delivery_channel || (identity.includes('@') ? 'EMAIL' : 'SMS'));
      setStep('verify_otp');
      setResendCooldown(60);
      setOtp('');
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to request verification code. Please try again.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Step 2: Verify OTP
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanOtp = otp.trim();
    if (cleanOtp.length < 6) {
      setError('Please enter the full 6-digit verification code.');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await apiClient.verifyOtp(identity.trim(), cleanOtp);
      setStep('set_password');
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Invalid or expired verification code. Please request a new one.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Resend OTP
  const handleResendOtp = async () => {
    if (resendCooldown > 0 || isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      const resp = await apiClient.forgotPassword(identity.trim());
      setMaskedDestination(resp.destination || identity.trim());
      setResendCooldown(60);
      setSuccessMsg('A new verification code has been dispatched.');
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to resend code. Please try again in a moment.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Step 3: Set New Password
  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters long.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match. Please verify and re-enter.');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await apiClient.resetPassword(identity.trim(), otp.trim(), newPassword);
      setStep('success');
      setPassword('');
      setOtp('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to reset password. Please restart the recovery process.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Switch to login
  const resetToLogin = () => {
    setStep('login');
    setError(null);
    setSuccessMsg(null);
    setPassword('');
    setOtp('');
    setNewPassword('');
    setConfirmPassword('');
  };

  const isPasswordValid = newPassword.length >= 8;
  const doPasswordsMatch = newPassword.length > 0 && newPassword === confirmPassword;

  const isLogin = step === 'login';

  return (
    <div className="relative min-h-screen lg:flex font-portal text-on-surface bg-white">
      <LoginBrandPanel />

      {/* Right panel (white) with the curved diagonal edge on desktop */}
      <main className="relative lg:ml-auto lg:w-[40.8%] bg-white flex flex-col justify-center max-lg:-mt-5 max-lg:rounded-t-3xl px-6 py-8 md:px-14 lg:pt-[3.9vw] lg:pb-10 lg:pl-[1.7vw] lg:pr-[3.2vw] lg:min-h-screen">
        <svg
          className="hidden lg:block absolute top-0 right-[calc(100%-1px)] h-full w-[calc(3.77vw+1px)] pointer-events-none"
          viewBox="0 0 63 941"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d="M63 0 L50 0 C20 120 0 300 0 440 C0 600 25 800 63 941 Z" fill="#ffffff" />
        </svg>

        <div className="w-full max-w-[600px] mx-auto lg:mx-0">
          {/* Header Texts */}
          <div className="mb-space-6 lg:mb-[41px]">
            {isLogin && (
              <p className="font-portal text-[13px] lg:text-[15px] tracking-[0.2em] text-[#5b6577] uppercase mb-2">
                Welcome to
              </p>
            )}
            <h1 className="font-portal text-[34px] lg:text-[clamp(34px,2.55vw,50px)] leading-[1.1] font-extrabold text-primary tracking-[-0.01em] mb-space-2">
              {step === 'login' && 'Command Portal'}
              {step === 'request_otp' && 'Reset Password'}
              {step === 'verify_otp' && 'Verify Code'}
              {step === 'set_password' && 'New Password'}
              {step === 'success' && 'Password Updated'}
            </h1>
            <p className="font-portal text-[15px] lg:text-[clamp(15px,1.14vw,22px)] text-[#5b6577]">
              {step === 'login' && 'Sign in to manage your operations, teams and field data.'}
              {step === 'request_otp' && 'Enter your email or mobile number to receive a 6-digit OTP.'}
              {step === 'verify_otp' && 'Enter the 6-digit security code dispatched to your device.'}
              {step === 'set_password' && 'Create a new secure password for your account.'}
              {step === 'success' && 'Your credentials have been securely updated.'}
            </p>
          </div>

          {/* Feedback Alerts */}
          {error && (
            <div
              role="alert"
              className="mb-space-4 p-space-3 bg-error-container border border-error text-on-error-container rounded-xl font-body-md text-xs animate-in fade-in-0 duration-200"
            >
              {error}
            </div>
          )}

          {sessionExpiredNotice && !error && step === 'login' && (
            <div
              role="status"
              className="mb-space-4 p-space-3 bg-secondary-fixed border border-secondary-fixed-dim text-on-secondary-fixed rounded-xl font-body-md text-xs"
            >
              Your session has expired. Please sign in again.
            </div>
          )}

          {passwordChangedNotice && !error && step === 'login' && (
            <div
              role="status"
              className="mb-space-4 p-space-3 bg-secondary-fixed border border-secondary-fixed-dim text-on-secondary-fixed rounded-xl font-body-md text-xs"
            >
              Your password was changed. Please sign in with your new password.
            </div>
          )}

          {successMsg && (
            <div
              role="status"
              className="mb-space-4 p-space-3 bg-primary-container border border-primary text-on-primary-container rounded-xl font-body-md text-xs flex items-center animate-in fade-in-0 duration-200"
            >
              <CheckCircle2 className="w-4 h-4 mr-2 shrink-0 text-primary" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* ================================================================= */}
          {/* 1. LOGIN MODE */}
          {/* ================================================================= */}
          {step === 'login' && (
            <>
            <form onSubmit={handleLoginSubmit} className="space-y-6">
              <Input
                variant="portal"
                label="WORK EMAIL OR MOBILE"
                type="text"
                required
                autoComplete="username"
                icon={isPhoneLike(identity) ? Smartphone : Mail}
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
                placeholder="Enter your work email or mobile number"
              />

              <div>
                <div className="flex items-center justify-between mb-space-1.5">
                  <label
                    htmlFor="login-password"
                    className="font-portal text-[13px] lg:text-[15px] text-primary uppercase tracking-[0.04em] block font-bold"
                  >
                    PASSWORD
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setStep('request_otp');
                      setError(null);
                      setSuccessMsg(null);
                    }}
                    className="font-portal text-[14px] lg:text-[16px] text-[#1a5fd0] underline underline-offset-2 hover:text-[#144aa3] focus:outline-none focus:ring-2 focus:ring-[#1a5fd0]/40 rounded font-medium"
                  >
                    Forgot Password?
                  </button>
                </div>
                <Input
                  variant="portal"
                  id="login-password"
                  type="password"
                  required
                  autoComplete="current-password"
                  icon={Lock}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                />
              </div>

              <Button
                type="submit"
                variant="secondary"
                size="lg"
                className="w-full !h-[56px] lg:!h-[64px] !rounded-md !bg-portal-orange hover:!bg-[#ff9a0a] !font-portal !text-[16px] lg:!text-[18px] !font-bold tracking-[0.02em] shadow-[0_6px_16px_rgba(255,163,30,0.3)] !mt-[26px]"
                isLoading={isSubmitting}
              >
                <span className="inline-flex items-center gap-3 whitespace-nowrap">
                  {isSubmitting ? 'Authenticating...' : 'Sign In To Command Center'}
                  {!isSubmitting && <ArrowRight className="w-5 h-5" aria-hidden="true" />}
                </span>
              </Button>
            </form>

            <div className="flex items-center gap-4 mt-7 mb-6 lg:mt-9 lg:mb-[26px] lg:-mx-2.5" role="separator" aria-label="or">
              <span className="h-px flex-1 bg-[#e4eaf1]" />
              <span className="font-portal text-[13px] font-semibold tracking-wider text-[#5b6577]">OR</span>
              <span className="h-px flex-1 bg-[#e4eaf1]" />
            </div>

            <ApkDownloadCard className="lg:-mx-2.5 lg:w-auto" />
            </>
          )}

          {/* ================================================================= */}
          {/* 2. STEP 1: REQUEST OTP */}
          {/* ================================================================= */}
          {step === 'request_otp' && (
            <form onSubmit={handleRequestOtp} className="space-y-space-4">
              <Input
                variant="portal"
                label="WORK EMAIL OR MOBILE"
                type="text"
                required
                autoComplete="username"
                icon={isPhoneLike(identity) ? Smartphone : Mail}
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
                placeholder="name@company.com or 9876543210"
              />

              <Button
                type="submit"
                variant="secondary"
                size="lg"
                className="w-full mt-space-2"
                isLoading={isSubmitting}
              >
                <span>{isSubmitting ? 'Generating Security Code...' : 'Send Verification Code (OTP)'}</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>

              <div className="mt-space-6 flex flex-col space-y-space-3 items-center">
                <button
                  type="button"
                  onClick={resetToLogin}
                  className="text-on-surface-variant hover:text-on-surface text-sm font-semibold flex items-center gap-1"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Return to Sign In</span>
                </button>
              </div>
            </form>
          )}

          {/* ================================================================= */}
          {/* 3. STEP 2: VERIFY OTP */}
          {/* ================================================================= */}
          {step === 'verify_otp' && (
            <form onSubmit={handleVerifyOtp} className="space-y-space-4">
              <div className="p-3 bg-surface-container border border-outline-variant rounded-xl text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-primary uppercase tracking-wider">
                    {deliveryChannel === 'SMS' ? 'SMS Code Sent' : 'Email Code Sent'}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setStep('request_otp');
                      setError(null);
                      setSuccessMsg(null);
                    }}
                    className="text-primary hover:underline font-medium"
                  >
                    Change
                  </button>
                </div>
                <div className="font-mono text-sm text-on-surface font-medium">
                  {maskedDestination || identity}
                </div>
              </div>

              <div>
                <Input
                  variant="portal"
                  label="6-DIGIT VERIFICATION CODE"
                  type="text"
                  required
                  maxLength={6}
                  autoFocus
                  icon={KeyRound}
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/[^\d]/g, '').slice(0, 6))}
                  placeholder="e.g. 123456"
                  className="font-mono text-center tracking-widest text-lg font-bold"
                />
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-on-surface-variant">Didn't receive the code?</span>
                {resendCooldown > 0 ? (
                  <span className="text-on-surface-variant font-mono font-medium">
                    Resend in {resendCooldown}s
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={handleResendOtp}
                    disabled={isSubmitting}
                    className="text-primary hover:underline font-semibold flex items-center gap-1"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Resend Code</span>
                  </button>
                )}
              </div>

              <Button
                type="submit"
                variant="secondary"
                size="lg"
                className="w-full mt-space-2"
                disabled={otp.trim().length < 6}
                isLoading={isSubmitting}
              >
                <span>{isSubmitting ? 'Verifying Code...' : 'Verify Code'}</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>

              <div className="mt-space-4 flex justify-center">
                <button
                  type="button"
                  onClick={resetToLogin}
                  className="text-on-surface-variant hover:text-on-surface text-sm font-semibold flex items-center gap-1"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Cancel</span>
                </button>
              </div>
            </form>
          )}

          {/* ================================================================= */}
          {/* 4. STEP 3: SET NEW PASSWORD */}
          {/* ================================================================= */}
          {step === 'set_password' && (
            <form onSubmit={handleResetPassword} className="space-y-space-4">
              <div className="relative">
                <Input
                  variant="portal"
                  label="NEW PASSWORD"
                  type="password"
                  required
                  icon={Lock}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  minLength={8}
                />
              </div>

              <div className="relative">
                <Input
                  variant="portal"
                  label="CONFIRM NEW PASSWORD"
                  type="password"
                  required
                  icon={Lock}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-type new password"
                />
              </div>

              {/* Password Requirement Indicators */}
              <div className="space-y-1.5 p-3 bg-surface-container rounded-xl text-xs">
                <div className="flex items-center gap-2">
                  {isPasswordValid ? (
                    <Check className="w-3.5 h-3.5 text-success" />
                  ) : (
                    <X className="w-3.5 h-3.5 text-on-surface-variant" />
                  )}
                  <span className={isPasswordValid ? 'text-success font-medium' : 'text-on-surface-variant'}>
                    At least 8 characters
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  {doPasswordsMatch ? (
                    <Check className="w-3.5 h-3.5 text-success" />
                  ) : (
                    <X className="w-3.5 h-3.5 text-on-surface-variant" />
                  )}
                  <span className={doPasswordsMatch ? 'text-success font-medium' : 'text-on-surface-variant'}>
                    Passwords match
                  </span>
                </div>
              </div>

              <Button
                type="submit"
                variant="secondary"
                size="lg"
                className="w-full mt-space-2"
                disabled={!isPasswordValid || !doPasswordsMatch}
                isLoading={isSubmitting}
              >
                <span>{isSubmitting ? 'Updating Password...' : 'Save New Password'}</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>

              <div className="mt-space-4 flex justify-center">
                <button
                  type="button"
                  onClick={resetToLogin}
                  className="text-on-surface-variant hover:text-on-surface text-sm font-semibold flex items-center gap-1"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Cancel</span>
                </button>
              </div>
            </form>
          )}

          {/* ================================================================= */}
          {/* 5. STEP 4: SUCCESS STATE */}
          {/* ================================================================= */}
          {step === 'success' && (
            <div className="space-y-space-6 text-center py-space-4 animate-in fade-in-0 zoom-in-95 duration-200">
              <div className="w-16 h-16 bg-success/10 border border-success/30 rounded-2xl flex items-center justify-center text-success mx-auto shadow-sm">
                <CheckCircle2 className="w-8 h-8 text-success" />
              </div>

              <div className="space-y-2">
                <h3 className="font-headline-md text-xl font-bold text-primary">
                  Password Updated Successfully
                </h3>
                <p className="font-body-md text-xs text-on-surface-variant max-w-xs mx-auto">
                  Your password has been changed. All active sessions have been revoked. You can now sign in with your new credentials.
                </p>
              </div>

              <Button
                type="button"
                variant="secondary"
                size="lg"
                onClick={resetToLogin}
                icon={ArrowRight}
                iconPosition="right"
                className="w-full whitespace-nowrap"
              >
                Back to Sign In
              </Button>
            </div>
          )}

        </div>
      </main>
    </div>
  );
};

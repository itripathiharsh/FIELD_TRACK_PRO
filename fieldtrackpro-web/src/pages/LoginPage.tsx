import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  ArrowRight,
  Lock,
  Mail,
  Smartphone,
  ShieldAlert,
  KeyRound,
  CheckCircle2,
  Eye,
  EyeOff,
  RefreshCw,
  ArrowLeft,
  Check,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { apiClient } from '../api/client';

type RecoveryStep = 'login' | 'request_otp' | 'verify_otp' | 'set_password' | 'success';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [step, setStep] = useState<RecoveryStep>('login');

  // Input states
  const [identity, setIdentity] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [otp, setOtp] = useState('');
  const [maskedDestination, setMaskedDestination] = useState<string | null>(null);
  const [deliveryChannel, setDeliveryChannel] = useState<'EMAIL' | 'SMS' | null>(null);

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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
      navigate(user.role === 'ADMIN' ? '/' : '/visits', { replace: true });
    } catch (err: any) {
      if (
        err?.code === 'AUTH_ACCOUNT_DISABLED' ||
        err?.message?.toLowerCase().includes('account is disabled') ||
        err?.message?.toLowerCase().includes('account disabled') ||
        err?.message?.toLowerCase().includes('deactivated')
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
    } catch (err: any) {
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
    } catch (err: any) {
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
    } catch (err: any) {
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
    } catch (err: any) {
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

  return (
    <div className="min-h-screen bg-surface-container-highest flex items-center justify-center p-space-4 md:p-space-8 font-body-md text-on-surface select-none">
      <div className="max-w-4xl w-full bg-surface-container-lowest border border-outline-variant rounded-2xl shadow-xl overflow-hidden grid grid-cols-1 md:grid-cols-2 animate-in fade-in-0 zoom-in-95 duration-300">
        
        {/* Left Hero Panel (Corporate Navy Identity) */}
        <div className="bg-primary p-space-8 md:p-space-12 text-on-primary flex flex-col justify-between relative overflow-hidden">
          <div className="absolute inset-0 opacity-10 bg-[radial-gradient(#ffffff_1px,transparent_1px)] [background-size:16px_16px] pointer-events-none" />

          <div>
            <div className="flex items-center gap-space-3 mb-space-8">
              <div className="w-10 h-10 bg-secondary-container rounded-xl flex items-center justify-center text-primary shadow-sm shrink-0">
                <ShieldCheck className="w-6 h-6 text-primary" />
              </div>
              <span className="font-headline-lg text-xl font-bold tracking-tight text-on-primary">
                FieldTrack Pro
              </span>
            </div>

            <h2 className="font-headline-lg text-2xl font-bold mb-space-3 leading-tight">
              Precision Field Intelligence
            </h2>
            <p className="font-body-lg text-sm text-inverse-primary/90 leading-relaxed">
              Enterprise geolocation verification, real-time telemetry, and field force command
              center.
            </p>
          </div>

          <div className="mt-space-8 pt-space-6 border-t border-primary-container/80 transition-all duration-200">
            <div className="flex items-center gap-space-2 text-secondary-container font-label-md text-xs font-bold uppercase tracking-wider">
              <ShieldAlert className="w-4 h-4 shrink-0 text-secondary-container" />
              <span>Secure Authentication</span>
            </div>
            <p className="text-xs text-inverse-primary/80 font-caption mt-space-1.5 leading-relaxed">
              Protected by multi-tier rate limiting, token rotation, and single-use security codes.
            </p>
          </div>
        </div>

        {/* Right Interactive Form Panel */}
        <div className="p-space-8 md:p-space-10 flex flex-col justify-center bg-surface-container-lowest">
          
          {/* Header Texts */}
          <div className="mb-space-6">
            <h1 className="font-headline-md text-2xl font-bold text-primary mb-space-1">
              {step === 'login' && 'Command Portal'}
              {step === 'request_otp' && 'Reset Password'}
              {step === 'verify_otp' && 'Verify Code'}
              {step === 'set_password' && 'New Password'}
              {step === 'success' && 'Password Updated'}
            </h1>
            <p className="font-caption text-xs text-on-surface-variant">
              {step === 'login' && 'Sign in using your registered email address or mobile number.'}
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
            <form onSubmit={handleLoginSubmit} className="space-y-space-4">
              <Input
                label="WORK EMAIL OR MOBILE"
                type="text"
                required
                autoComplete="username"
                icon={identity.includes('@') ? Mail : Smartphone}
                value={identity}
                onChange={(e) => setIdentity(e.target.value)}
                placeholder="name@company.com or 9876543210"
              />

              <div>
                <div className="flex items-center justify-between mb-space-1">
                  <label
                    htmlFor="login-password"
                    className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold"
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
                    className="text-primary hover:text-primary/80 font-body-sm text-xs focus:outline-none focus:underline font-medium"
                  >
                    Forgot Password?
                  </button>
                </div>
                <div className="relative">
                  <Input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    autoComplete="current-password"
                    icon={Lock}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface p-1"
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <Button
                type="submit"
                variant="secondary"
                size="lg"
                className="w-full mt-space-2"
                isLoading={isSubmitting}
              >
                <span>{isSubmitting ? 'Authenticating...' : 'Sign In To Command Center'}</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </form>
          )}

          {/* ================================================================= */}
          {/* 2. STEP 1: REQUEST OTP */}
          {/* ================================================================= */}
          {step === 'request_otp' && (
            <form onSubmit={handleRequestOtp} className="space-y-space-4">
              <Input
                label="WORK EMAIL OR MOBILE"
                type="text"
                required
                autoComplete="username"
                icon={identity.includes('@') ? Mail : Smartphone}
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
                  label="NEW PASSWORD"
                  type={showNewPassword ? 'text' : 'password'}
                  required
                  icon={Lock}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  minLength={8}
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-9 text-on-surface-variant hover:text-on-surface p-1"
                >
                  {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              <div className="relative">
                <Input
                  label="CONFIRM NEW PASSWORD"
                  type={showConfirmPassword ? 'text' : 'password'}
                  required
                  icon={Lock}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-type new password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-9 text-on-surface-variant hover:text-on-surface p-1"
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
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
                className="w-full"
              >
                <span>Back to Sign In</span>
                <ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};

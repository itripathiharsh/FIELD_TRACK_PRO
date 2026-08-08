import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowRight, Lock, Mail, ShieldAlert } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';

/**
 * Sign-in screen.
 *
 * FT-060 / FT-038: the demo role selector has been removed. It offered ADMIN /
 * MANAGER / FIELD REP presets with a pre-filled password; MANAGER is not a role
 * the backend recognises, and the selector only changed which credentials were
 * typed in - it granted nothing by itself. Combined with FT-001 it created the
 * impression that picking a role logged you in as that role.
 *
 * The role now comes from the server after authentication, and nothing else.
 * The approved visual design (navy hero panel, amber primary action, League
 * Spartan / Libre Baskerville type) is unchanged.
 */
export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [identity, setIdentity] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const user = await login(identity.trim(), password);
      // Destination follows the role the SERVER reported.
      navigate(user.role === 'ADMIN' ? '/' : '/visits', { replace: true });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Authentication failed. Please check your credentials.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

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
              <span>Secure Access</span>
            </div>
            <p className="text-xs text-inverse-primary/80 font-caption mt-space-1.5 leading-relaxed">
              Your access level is determined by your account and applied by the server on every
              request.
            </p>
          </div>
        </div>

        {/* Right Form Panel */}
        <div className="p-space-8 md:p-space-10 flex flex-col justify-center bg-surface-container-lowest">
          <div className="mb-space-6">
            <h1 className="font-headline-md text-2xl font-bold text-primary mb-space-1">
              Command Portal
            </h1>
            <p className="font-caption text-xs text-on-surface-variant">
              Sign in to access your operational telemetry dashboard.
            </p>
          </div>

          {error && (
            <div
              role="alert"
              className="mb-space-4 p-space-3 bg-error-container border border-error text-on-error-container rounded-xl font-body-md text-xs animate-in fade-in-0 duration-200"
            >
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-space-4">
            <Input
              label="WORK EMAIL OR MOBILE"
              type="text"
              required
              autoComplete="username"
              icon={Mail}
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              placeholder="you@company.com"
            />

            <div>
              <div className="flex items-center justify-between mb-space-1">
                <label
                  htmlFor="login-password"
                  className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold"
                >
                  PASSWORD
                </label>
              </div>
              <Input
                id="login-password"
                type="password"
                required
                autoComplete="current-password"
                icon={Lock}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
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
        </div>
      </div>
    </div>
  );
};

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowRight, Lock, Mail, ShieldAlert, KeyRound } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';

type RolePreset = 'ADMIN' | 'MANAGER' | 'EMPLOYEE';

interface PresetInfo {
  label: string;
  email: string;
  badge: string;
  description: string;
}

const PRESETS: Record<RolePreset, PresetInfo> = {
  ADMIN: {
    label: 'Admin',
    email: 'admin@fieldtrackpro.com',
    badge: 'System Administration',
    description: 'Full executive command, user provisioning, and system policy control access.',
  },
  MANAGER: {
    label: 'Manager',
    email: 'manager@fieldtrackpro.com',
    badge: 'Regional Dispatch',
    description: 'Territory management, field agent dispatching, and audit telemetry oversight.',
  },
  EMPLOYEE: {
    label: 'Field Rep',
    email: 'john@fieldtrackpro.com',
    badge: 'Field Operations',
    description: 'Personal visit schedule, GPS check-in execution, and site photo submission.',
  },
};

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [activeRole, setActiveRole] = useState<RolePreset>('ADMIN');
  const [email, setEmail] = useState(PRESETS.ADMIN.email);
  const [password, setPassword] = useState('Secret@1234');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleRoleChange = (role: RolePreset) => {
    setActiveRole(role);
    setEmail(PRESETS[role].email);
    setPassword('Secret@1234');
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
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
              <span className="font-headline-lg text-xl font-bold tracking-tight text-on-primary">FieldTrack Pro</span>
            </div>

            <h2 className="font-headline-lg text-2xl font-bold mb-space-3 leading-tight">
              Precision Field Intelligence
            </h2>
            <p className="font-body-lg text-sm text-inverse-primary/90 leading-relaxed">
              Enterprise geolocation verification, real-time telemetry, and field force command center.
            </p>
          </div>

          <div className="mt-space-8 pt-space-6 border-t border-primary-container/80 transition-all duration-200">
            <div className="flex items-center gap-space-2 text-secondary-container font-label-md text-xs font-bold uppercase tracking-wider">
              <ShieldAlert className="w-4 h-4 shrink-0 text-secondary-container" />
              <span>{PRESETS[activeRole].badge}</span>
            </div>
            <p className="text-xs text-inverse-primary/80 font-caption mt-space-1.5 leading-relaxed">
              {PRESETS[activeRole].description}
            </p>
          </div>
        </div>

        {/* Right Form Panel */}
        <div className="p-space-8 md:p-space-10 flex flex-col justify-center bg-surface-container-lowest">
          <div className="mb-space-6">
            <h1 className="font-headline-md text-2xl font-bold text-primary mb-space-1">Command Portal</h1>
            <p className="font-caption text-xs text-on-surface-variant">
              Sign in to access your operational telemetry dashboard.
            </p>
          </div>

          {/* Segmented Control Role Selector */}
          <div className="mb-space-6">
            <div className="flex items-center justify-between mb-space-2">
              <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                SELECT OPERATIONAL ROLE
              </label>
              <span className="font-caption text-[11px] text-secondary font-medium">Demo Presets</span>
            </div>

            <div
              role="tablist"
              aria-label="Role selector"
              className="grid grid-cols-3 gap-1 p-1 bg-surface-container-low border border-outline-variant/80 rounded-xl relative"
            >
              {(['ADMIN', 'MANAGER', 'EMPLOYEE'] as RolePreset[]).map((role) => {
                const isSelected = activeRole === role;
                return (
                  <button
                    key={role}
                    type="button"
                    role="tab"
                    aria-selected={isSelected}
                    onClick={() => handleRoleChange(role)}
                    className={`py-2 px-3 rounded-lg font-button text-xs uppercase tracking-wider font-bold transition-all duration-200 cursor-pointer text-center relative z-10 ${
                      isSelected
                        ? 'bg-primary text-on-primary shadow-xs'
                        : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container/60 active:scale-95'
                    }`}
                  >
                    {PRESETS[role].label}
                  </button>
                );
              })}
            </div>
          </div>

          {error && (
            <div className="mb-space-4 p-space-3 bg-error-container border border-error text-on-error-container rounded-xl font-body-md text-xs animate-in fade-in-0 duration-200">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-space-4">
            <Input
              label="WORK EMAIL"
              type="email"
              required
              icon={Mail}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@fieldtrackpro.com"
            />

            <div>
              <div className="flex items-center justify-between mb-space-1">
                <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                  PASSWORD
                </label>
                <a href="#forgot" onClick={(e) => e.preventDefault()} className="font-caption text-xs text-secondary hover:underline font-medium">
                  Forgot?
                </a>
              </div>
              <Input
                type="password"
                required
                icon={Lock}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-space-2 pt-space-1">
              <input
                type="checkbox"
                id="remember"
                defaultChecked
                className="w-4 h-4 rounded border-outline-variant text-primary-container focus:ring-primary-container cursor-pointer"
              />
              <label htmlFor="remember" className="font-caption text-xs text-on-surface-variant cursor-pointer">
                Remember authentication state for 30 days
              </label>
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

            <Button
              type="button"
              variant="outline"
              size="md"
              icon={KeyRound}
              className="w-full mt-space-2"
            >
              Enterprise SSO Sign In
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
};

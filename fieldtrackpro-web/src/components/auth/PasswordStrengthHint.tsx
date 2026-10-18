import React from 'react';
import { passwordStrength } from '../../utils/passwordRules';

const BAR_COLORS = ['bg-error', 'bg-error', 'bg-amber-500', 'bg-emerald-500', 'bg-emerald-600'];

/** Advisory strength meter under a "new password" field. Renders nothing for an empty value. */
export const PasswordStrengthHint: React.FC<{ password: string }> = ({ password }) => {
  if (!password) return null;
  const { level, label } = passwordStrength(password);
  return (
    <div className="mt-1.5" data-testid="password-strength">
      <div className="flex gap-1" aria-hidden="true">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className={`h-1.5 flex-1 rounded-full ${i < level ? BAR_COLORS[level] : 'bg-outline-variant/50'}`}
          />
        ))}
      </div>
      <p className="mt-1 text-xs text-on-surface-variant" role="status">
        Strength: <span className="font-semibold">{label}</span>
      </p>
    </div>
  );
};

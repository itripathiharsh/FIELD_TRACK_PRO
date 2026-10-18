import React, { useState } from 'react';
import { Eye, EyeOff, X } from 'lucide-react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: React.ElementType;
  onClear?: () => void;
  /** 'portal' = large login-portal styling. */
  variant?: 'default' | 'portal';
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({
  label,
  error,
  helperText,
  icon: Icon,
  type = 'text',
  className = '',
  id,
  value,
  onChange,
  onClear,
  disabled,
  variant = 'default',
  ...props
}, ref) => {
  const [showPassword, setShowPassword] = useState(false);
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const isPassword = type === 'password';
  const currentType = isPassword ? (showPassword ? 'text' : 'password') : type;

  const portal = variant === 'portal';

  return (
    <div className="w-full flex flex-col gap-space-1.5">
      {label && (
        <label htmlFor={inputId} className={portal ? 'font-portal text-[13px] lg:text-[15px] text-primary uppercase tracking-[0.04em] block font-bold mb-1' : 'font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold'}>
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {Icon && (
          <div className={`absolute ${portal ? 'left-4 text-[#445068]' : 'left-space-3 text-on-surface-variant'} pointer-events-none shrink-0`}>
            <Icon className={portal ? 'w-5 h-5' : 'w-4 h-4'} />
          </div>
        )}
        <input
          id={inputId}
          ref={ref}
          type={currentType}
          value={value}
          onChange={onChange}
          disabled={disabled}
          className={`w-full ${portal ? 'h-[54px] lg:h-[58px] bg-portal-field rounded-md font-portal text-[15px] sm:text-[17px] placeholder:text-[#7c8798]' : 'h-10 bg-surface rounded-lg font-body-md text-sm placeholder:text-outline'} border ${Icon ? (portal ? 'pl-12' : 'pl-space-9') : 'px-space-3'} ${
            isPassword || (onClear && value) ? (portal ? 'pr-12' : 'pr-space-9') : 'pr-space-3'
          } text-on-surface focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all ${
            error ? 'border-error focus:border-error focus:ring-error/20' : portal ? 'border-portal-field-border' : 'border-outline-variant'
          } ${disabled ? 'opacity-60 bg-surface-container-low cursor-not-allowed' : ''} ${className}`}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className={`absolute ${portal ? 'right-4 text-[#445068]' : 'right-space-3 text-on-surface-variant'} hover:text-on-surface transition-colors p-0.5 rounded focus:outline-none focus:ring-1 focus:ring-primary-container cursor-pointer`}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? <EyeOff className={portal ? 'w-5 h-5' : 'w-4 h-4'} /> : <Eye className={portal ? 'w-5 h-5' : 'w-4 h-4'} />}
          </button>
        )}
        {!isPassword && onClear && value && (
          <button
            type="button"
            onClick={onClear}
            className="absolute right-space-3 text-on-surface-variant hover:text-on-surface transition-colors p-0.5 rounded focus:outline-none cursor-pointer"
            aria-label="Clear input"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      {error && <p className="font-caption text-xs text-error font-medium flex items-center gap-1">{error}</p>}
      {helperText && !error && <p className="font-caption text-xs text-on-surface-variant">{helperText}</p>}
    </div>
  );
});

Input.displayName = 'Input';

import React, { useState } from 'react';
import { Eye, EyeOff, X } from 'lucide-react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: React.ElementType;
  onClear?: () => void;
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
  ...props
}, ref) => {
  const [showPassword, setShowPassword] = useState(false);
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);
  const isPassword = type === 'password';
  const currentType = isPassword ? (showPassword ? 'text' : 'password') : type;

  return (
    <div className="w-full flex flex-col gap-space-1.5">
      {label && (
        <label htmlFor={inputId} className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {Icon && (
          <div className="absolute left-space-3 text-on-surface-variant pointer-events-none shrink-0">
            <Icon className="w-4 h-4" />
          </div>
        )}
        <input
          id={inputId}
          ref={ref}
          type={currentType}
          value={value}
          onChange={onChange}
          disabled={disabled}
          className={`w-full h-10 bg-surface border rounded-lg ${Icon ? 'pl-space-9' : 'px-space-3'} ${
            isPassword || (onClear && value) ? 'pr-space-9' : 'pr-space-3'
          } text-on-surface font-body-md text-sm placeholder:text-outline focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all ${
            error ? 'border-error focus:border-error focus:ring-error/20' : 'border-outline-variant'
          } ${disabled ? 'opacity-60 bg-surface-container-low cursor-not-allowed' : ''} ${className}`}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-space-3 text-on-surface-variant hover:text-on-surface transition-colors p-0.5 rounded focus:outline-none focus:ring-1 focus:ring-primary-container cursor-pointer"
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
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

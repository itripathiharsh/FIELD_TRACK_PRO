import React from 'react';

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(({
  label,
  error,
  helperText,
  className = '',
  id,
  children,
  disabled,
  ...props
}, ref) => {
  const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="w-full flex flex-col gap-space-1.5">
      {label && (
        <label htmlFor={selectId} className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
          {label}
        </label>
      )}
      <select
        id={selectId}
        ref={ref}
        disabled={disabled}
        className={`w-full h-10 bg-surface border rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all cursor-pointer ${
          error ? 'border-error focus:border-error focus:ring-error/20' : 'border-outline-variant'
        } ${disabled ? 'opacity-60 bg-surface-container-low cursor-not-allowed' : ''} ${className}`}
        {...props}
      >
        {children}
      </select>
      {error && <p className="font-caption text-xs text-error font-medium">{error}</p>}
      {helperText && !error && <p className="font-caption text-xs text-on-surface-variant">{helperText}</p>}
    </div>
  );
});

Select.displayName = 'Select';
